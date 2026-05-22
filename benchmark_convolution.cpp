#include <iostream>
#include <vector>
#include <random>
#include <chrono>

// Define a massive high-resolution image (e.g., 8K resolution)
const int WIDTH = 7680;  // 8K resolution
const int HEIGHT = 4320;
const int KERNEL_SIZE = 15; 

void apply_heavy_blur(const std::vector<float>& src, std::vector<float>& dst) {
    int offset = KERNEL_SIZE / 2;
    
    // The auto-parallelizer will target this outer loop
    for (int y = offset; y < HEIGHT - offset; y++) {
        for (int x = offset; x < WIDTH - offset; x++) {
            float sum = 0.0f;
            
            // Apply the kernel
            for (int ky = -offset; ky <= offset; ky++) {
                for (int kx = -offset; kx <= offset; kx++) {
                    int pixel_idx = (y + ky) * WIDTH + (x + kx);
                    sum += src[pixel_idx]; 
                }
            }
            // Normalize and assign (no cross-iteration dependencies)
            dst[y * WIDTH + x] = sum / (KERNEL_SIZE * KERNEL_SIZE);
        }
    }
}

int main() {
    std::cout << "Allocating memory for 4K image..." << std::endl;
    std::vector<float> source_image(WIDTH * HEIGHT);
    std::vector<float> dest_image(WIDTH * HEIGHT, 0.0f);

    // Populate with random noise
    std::mt19937 gen(42);
    std::uniform_real_distribution<float> dis(0.0f, 255.0f);
    for (int i = 0; i < WIDTH * HEIGHT; i++) {
        source_image[i] = dis(gen);
    }

    std::cout << "Starting heavy convolution processing..." << std::endl;
    
    auto start = std::chrono::high_resolution_clock::now();
    apply_heavy_blur(source_image, dest_image);
    auto end = std::chrono::high_resolution_clock::now();
    
    std::chrono::duration<double> diff = end - start;
    std::cout << "Execution Time: " << diff.count() << " seconds\n";

    // Prevent compiler optimization from eliminating the calculation
    std::cout << "Checksum: " << dest_image[(HEIGHT/2) * WIDTH + (WIDTH/2)] << std::endl;

    return 0;
}