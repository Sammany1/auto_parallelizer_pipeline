import sys
import os
import clang.cindex
from clang.cindex import CursorKind

# ==========================================
# CONFIGURATION
# ==========================================
# Set the path to the libclang library based on OS
if sys.platform == 'darwin': # macOS (Homebrew LLVM)
    clang.cindex.Config.set_library_path('/opt/homebrew/opt/llvm/lib')
elif sys.platform == 'linux': # Ubuntu/Docker
    # Linux usually finds it automatically, but specify if needed
    pass 

# ==========================================
# AST VISITOR PATTERN
# ==========================================
class LoopAnalyzer:
    def __init__(self, loop_node):
        self.loop_node = loop_node
        self.has_side_effects = False
        self.side_effect_reason = ""
        self.reductions = set()
        
        # Blacklisted function names (stateful or I/O)
        self.unsafe_functions = {'rand', 'printf', 'scanf', 'cout', 'cin', 'dis', 'gen'}

        # Cache the line range of this loop for scope checks
        self._loop_start = loop_node.extent.start.line
        self._loop_end   = loop_node.extent.end.line

        # Pre-collect all VAR_DECL names that live *inside* this loop body
        # so we can exclude them from reduction clauses.
        self._inner_decls = set()
        for n in loop_node.walk_preorder():
            if n.kind == CursorKind.VAR_DECL:
                self._inner_decls.add(n.spelling)

    def analyze(self):
        """Walks the AST nodes specifically inside this loop."""
        self._visit(self.loop_node)

        # FIX 2: Drop reduction variables that are declared *inside* this loop.
        # Such variables don't exist in the enclosing scope, so OpenMP would
        # reject them with "has not been declared".
        self.reductions -= self._inner_decls

        return not self.has_side_effects

    def _visit(self, node):
        # 1. Check for unsafe function calls (Side Effects)
        if node.kind == CursorKind.CALL_EXPR:
            func_name = node.spelling or node.displayname
            if any(unsafe in func_name for unsafe in self.unsafe_functions):
                self.has_side_effects = True
                self.side_effect_reason = f"Unsafe function call detected: '{func_name}'"
                return

        # 2. Detect Reductions (e.g., sum += ...)
        # We look for compound assignment operators in the AST
        if node.kind == CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
            # The first child of an assignment is the Left Hand Side (the variable)
            lhs = list(node.get_children())[0]
            if lhs.kind == CursorKind.DECL_REF_EXPR:
                var_name = lhs.spelling
                self.reductions.add(var_name)

        # Recursively visit children
        for child in node.get_children():
            self._visit(child)


# ==========================================
# COMPILER PIPELINE
# ==========================================
def compile_ast_parallel(input_filepath, output_filepath):
    print("=======================================")
    print(f" LLVM AST Auto-Parallelizer Initialized")
    print(f" Target: {input_filepath}")
    print("=======================================")

    index = clang.cindex.Index.create()
    
    # Parse the C++ file into an Abstract Syntax Tree
    translation_unit = index.parse(input_filepath, args=['-std=c++17'])

    # FIX 1: Only process loops in the user's own source file, not #included headers.
    user_file = os.path.realpath(input_filepath)

    # approved_loops: list of (extent_start, extent_end, inject_line, pragma)
    # Stored so we can detect and skip loops nested inside already-approved ones.
    # Injecting parallel pragmas on inner loops of an already-parallel outer loop
    # causes nested thread spawning: creating thousands of new thread teams per
    # outer iteration, which is catastrophically slower than sequential.
    approved_loops = []
    loop_count = 0

    # Walk the entire AST looking for FOR loops
    for node in translation_unit.cursor.walk_preorder():
        if node.kind == CursorKind.FOR_STMT:
            # Skip any loop whose location is inside a stdlib / system header
            if node.location.file is None:
                continue
            if os.path.realpath(node.location.file.name) != user_file:
                continue

            loop_count += 1
            line_num   = node.location.line
            ext_start  = node.extent.start.line
            ext_end    = node.extent.end.line
            print(f"\n[AST] Analyzing Loop #{loop_count} at line {line_num}...")

            # FIX 3: Skip loops nested inside an already-approved outer loop.
            # Nested #pragma omp parallel for creates a brand-new thread team for
            # every iteration of the outer parallel loop – thread-spawn overhead
            # then dominates and makes execution orders of magnitude slower.
            enclosing = next(
                (outer for outer in approved_loops
                 if outer[0] <= ext_start and ext_end <= outer[1]),
                None
            )
            if enclosing:
                print(f"  -> [SKIPPED] Nested inside parallel loop "
                      f"at line {enclosing[2]} – would cause nested thread spawning.")
                continue

            # Initialize our Semantic Analyzer for this specific loop
            analyzer = LoopAnalyzer(node)
            is_safe = analyzer.analyze()

            if not is_safe:
                print(f"  -> [REJECTED] {analyzer.side_effect_reason}")
                continue

            # Formulate the OpenMP Pragma
            pragma = "#pragma omp parallel for schedule(static)"
            if analyzer.reductions:
                red_str = ", ".join(analyzer.reductions)
                pragma += f" reduction(+:{red_str})"
                print(f"  -> [REDUCTION DETECTED] Variables: {red_str}")

            print("  -> [APPROVED] Loop is semantically independent.")
            approved_loops.append((ext_start, ext_end, line_num, pragma))

    # Build the injection map from approved outermost loops only
    injections = {line: pragma for (_, _, line, pragma) in approved_loops}


    # ==========================================
    # CODE GENERATION (Injecting pragmas)
    # ==========================================
    with open(input_filepath, 'r') as f:
        source_lines = f.readlines()

    output_lines = []
    # Rebuild the file, inserting pragmas at the exact AST line locations
    for i, line in enumerate(source_lines):
        current_line_num = i + 1
        if current_line_num in injections:
            # Preserve the original indentation
            indent = line[:len(line) - len(line.lstrip())]
            output_lines.append(f"{indent}{injections[current_line_num]}\n")
        output_lines.append(line)

    with open(output_filepath, 'w') as f:
        f.writelines(output_lines)

    print("\n=======================================")
    print(f" Compilation Complete! Output: {output_filepath}")
    print("=======================================")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 ast_compiler.py <input.cpp>")
        sys.exit(1)

    input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"Error: Could not find {input_file}")
        sys.exit(1)

    # Generate output filename automatically
    directory = os.path.dirname(input_file)
    filename = os.path.basename(input_file)

    output_file = os.path.join(directory, f"PARALLEL_{filename}")

    compile_ast_parallel(input_file, output_file)