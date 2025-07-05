# Ultra-Low Latency HFT System CMake Configuration
cmake_minimum_required(VERSION 3.16)
project(HFTSystem VERSION 1.0.0 LANGUAGES CXX)

# Set C++ standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Compiler optimizations for ultra-low latency
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -mtune=native -flto -ffast-math -DNDEBUG")
set(CMAKE_CXX_FLAGS_DEBUG "-O0 -g3 -fsanitize=address,undefined")

# Enable specific CPU features for maximum performance
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -mavx2 -mfma -mbmi2 -mlzcnt -mpopcnt")

# Default to Release build
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Find required packages
find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)

# Find DPDK
pkg_check_modules(DPDK REQUIRED libdpdk)

# Find NUMA library
find_library(NUMA_LIBRARY numa)
if(NOT NUMA_LIBRARY)
    message(FATAL_ERROR "NUMA library not found")
endif()

# Find OpenCL for FPGA acceleration (optional)
find_package(OpenCL QUIET)
if(OpenCL_FOUND)
    add_definitions(-DFPGA_ACCELERATION)
    message(STATUS "OpenCL found - FPGA acceleration enabled")
else()
    message(STATUS "OpenCL not found - FPGA acceleration disabled")
endif()

# Find TensorFlow Lite (optional)
find_path(TFLITE_INCLUDE_DIR tensorflow/lite/interpreter.h
    PATHS /usr/include /usr/local/include)
find_library(TFLITE_LIBRARY tensorflowlite
    PATHS /usr/lib /usr/local/lib)

if(TFLITE_INCLUDE_DIR AND TFLITE_LIBRARY)
    add_definitions(-DUSE_TENSORFLOW_LITE)
    message(STATUS "TensorFlow Lite found - ML acceleration enabled")
else()
    message(STATUS "TensorFlow Lite not found - ML acceleration disabled")
endif()

# Find Intel MKL (optional)
find_path(MKL_INCLUDE_DIR mkl.h
    PATHS /opt/intel/mkl/include /usr/include/mkl)
find_library(MKL_LIBRARY mkl_rt
    PATHS /opt/intel/mkl/lib /opt/intel/lib /usr/lib)

if(MKL_INCLUDE_DIR AND MKL_LIBRARY)
    add_definitions(-DUSE_INTEL_MKL)
    message(STATUS "Intel MKL found - optimized math enabled")
else()
    message(STATUS "Intel MKL not found - using standard math")
endif()

# AWS SDK (for existing cloud functionality)
find_package(AWSSDK QUIET COMPONENTS core dynamodb cloudwatch sns kinesis s3)

# Eigen3 for linear algebra
find_package(Eigen3 QUIET)

# Google Test for testing
find_package(GTest QUIET)

# Include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${DPDK_INCLUDE_DIRS}
)

if(OpenCL_FOUND)
    include_directories(${OpenCL_INCLUDE_DIRS})
endif()

if(TFLITE_INCLUDE_DIR)
    include_directories(${TFLITE_INCLUDE_DIR})
endif()

if(MKL_INCLUDE_DIR)
    include_directories(${MKL_INCLUDE_DIR})
endif()

# Core HFT system libraries
add_library(hft_networking STATIC
    src/core/dpdk_network_engine.cpp
    src/core/dpdk_network_engine.h
)

add_library(hft_data STATIC
    src/data/high_performance_order_book.cpp
    src/data/high_performance_order_book.h
)

add_library(hft_memory STATIC
    src/utils/numa_memory_manager.cpp
    src/utils/numa_memory_manager.h
)

add_library(hft_fpga STATIC
    src/fpga/fpga_risk_engine.cpp
    src/fpga/fpga_risk_engine.h
    src/fpga/fpga_interface.cpp
    src/fpga/fpga_interface.h
)

add_library(hft_ml STATIC
    src/ml/alpha_engine.cpp
    src/ml/alpha_engine.h
)

add_library(hft_testing STATIC
    src/testing/latency_benchmark.cpp
    src/testing/latency_benchmark.h
)

# Legacy cloud library (optional)
if(AWSSDK_FOUND)
    add_library(hft_core STATIC
        src/core/market_data_handler_aws.cpp
        src/core/trading_engine_aws.cpp
        src/risk/risk_manager_aws.cpp
        src/utils/aws_monitoring.cpp
    )
    
    target_link_libraries(hft_core
        ${AWSSDK_LINK_LIBRARIES}
        Threads::Threads
    )
    
    if(Eigen3_FOUND)
        target_link_libraries(hft_core Eigen3::Eigen)
    endif()
endif()

# Set library properties and link dependencies
set_target_properties(hft_networking PROPERTIES
    COMPILE_FLAGS "${DPDK_CFLAGS}")

target_link_libraries(hft_networking
    ${DPDK_LIBRARIES}
    Threads::Threads
)

target_link_libraries(hft_data
    hft_memory
    Threads::Threads
)

target_link_libraries(hft_memory
    ${NUMA_LIBRARY}
    Threads::Threads
)

target_link_libraries(hft_fpga
    hft_memory
    Threads::Threads
)

if(OpenCL_FOUND)
    target_link_libraries(hft_fpga ${OpenCL_LIBRARIES})
endif()

target_link_libraries(hft_ml
    hft_memory
    Threads::Threads
)

if(TFLITE_LIBRARY)
    target_link_libraries(hft_ml ${TFLITE_LIBRARY})
endif()

if(MKL_LIBRARY)
    target_link_libraries(hft_ml ${MKL_LIBRARY})
endif()

target_link_libraries(hft_testing
    hft_networking
    hft_data
    hft_memory
    hft_fpga
    hft_ml
    Threads::Threads
)

# Legacy strategy and execution libraries (optional)
if(AWSSDK_FOUND)
    target_include_directories(hft_core PUBLIC
        ${AWSSDK_INCLUDE_DIRS}
    )

    add_library(hft_strategies STATIC
        src/strategies/scalping_strategy.cpp
        src/strategies/momentum_strategy.cpp
        src/strategies/mean_reversion_strategy.cpp
        src/strategies/strategy_factory.cpp
        src/strategies/strategy_manager.cpp
    )

    target_link_libraries(hft_strategies
        hft_core
    )

    add_library(hft_execution STATIC
        src/execution/order_management_system.cpp
        src/execution/execution_engine.cpp
    )

    target_link_libraries(hft_execution
        hft_core
        ${AWSSDK_LINK_LIBRARIES}
    )
endif()

# Main HFT System executable
add_executable(hft_system
    src/main.cpp
)

# Link all HFT libraries
target_link_libraries(hft_system
    hft_networking
    hft_data
    hft_memory
    hft_fpga
    hft_ml
    hft_testing
    Threads::Threads
    rt  # Real-time library for clock functions
)

# Add legacy libraries if available
if(AWSSDK_FOUND)
    target_link_libraries(hft_system
        hft_core
        hft_strategies
        hft_execution
        ${AWSSDK_LINK_LIBRARIES}
    )
endif()

# Benchmark executable
add_executable(hft_benchmark
    src/benchmark_main.cpp
)

target_link_libraries(hft_benchmark
    hft_testing
    Threads::Threads
)

# Set performance optimizations
target_compile_options(hft_system PRIVATE
    -ffast-math
    -funroll-loops
    -finline-functions
    -fomit-frame-pointer
    -pipe
)

# Link-time optimizations for release builds
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_compile_options(hft_system PRIVATE -flto)
    target_link_options(hft_system PRIVATE -flto)
endif()

# Backtesting executable
add_executable(strategy_backtest
    tests/strategy_backtest.cpp
)

target_link_libraries(strategy_backtest
    hft_strategies
    hft_core
)

# Integration tests
add_executable(integration_tests
    tests/integration_test.cpp
)

target_link_libraries(integration_tests
    hft_core
    hft_strategies
    hft_execution
    GTest::GTest
    GTest::Main
)

# Unit tests for individual components
add_executable(unit_tests
    tests/unit_tests.cpp
)

target_link_libraries(unit_tests
    hft_core
    hft_strategies
    GTest::GTest
    GTest::Main
)

# Performance benchmarks
add_executable(performance_benchmark
    tests/performance_benchmark.cpp
)

target_link_libraries(performance_benchmark
    hft_core
    hft_strategies
    hft_execution
)

target_compile_options(performance_benchmark PRIVATE
    -O3
    -march=native
    -mtune=native
)

# Custom targets for different build types
add_custom_target(debug
    COMMAND ${CMAKE_COMMAND} -DCMAKE_BUILD_TYPE=Debug ${CMAKE_SOURCE_DIR}
    COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target all
    COMMENT "Building debug version"
)

add_custom_target(release
    COMMAND ${CMAKE_COMMAND} -DCMAKE_BUILD_TYPE=Release ${CMAKE_SOURCE_DIR}
    COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target all
    COMMENT "Building release version"
)

# Testing targets
enable_testing()

add_test(NAME unit_tests COMMAND unit_tests)
add_test(NAME integration_tests COMMAND integration_tests)
add_test(NAME strategy_backtest COMMAND strategy_backtest)

# Custom test target that runs all tests
add_custom_target(run_tests
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    DEPENDS unit_tests integration_tests strategy_backtest
    COMMENT "Running all tests"
)

# Performance test target
add_custom_target(run_performance_tests
    COMMAND ./performance_benchmark
    DEPENDS performance_benchmark
    COMMENT "Running performance benchmarks"
)

# Installation
install(TARGETS hft_system DESTINATION bin)
install(TARGETS strategy_backtest DESTINATION bin)
install(FILES config/aws_infrastructure.yaml DESTINATION etc/hft)
install(FILES deployment/cloudformation-hft-infrastructure.yml DESTINATION etc/hft)
install(FILES deployment/deploy-hft-system.sh DESTINATION bin
        PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE)

# Documentation target (requires Doxygen)
find_package(Doxygen)
if(DOXYGEN_FOUND)
    set(DOXYGEN_IN ${CMAKE_CURRENT_SOURCE_DIR}/docs/Doxyfile.in)
    set(DOXYGEN_OUT ${CMAKE_CURRENT_BINARY_DIR}/Doxyfile)
    
    configure_file(${DOXYGEN_IN} ${DOXYGEN_OUT} @ONLY)
    
    add_custom_target(docs
        COMMAND ${DOXYGEN_EXECUTABLE} ${DOXYGEN_OUT}
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "Generating API documentation with Doxygen"
        VERBATIM
    )
endif()

# Packaging
set(CPACK_PACKAGE_NAME "HFTSystem")
set(CPACK_PACKAGE_VERSION "1.0.0")
set(CPACK_PACKAGE_DESCRIPTION "High-Frequency Trading System")
set(CPACK_PACKAGE_CONTACT "trading@yourcompany.com")
set(CPACK_GENERATOR "DEB;RPM;TGZ")

include(CPack)

# Print configuration summary
message(STATUS "=== HFT System Build Configuration ===")
message(STATUS "Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "AWS SDK Found: ${AWSSDK_FOUND}")
message(STATUS "Eigen3 Found: ${Eigen3_FOUND}")
message(STATUS "GTest Found: ${GTest_FOUND}")
message(STATUS "Install Prefix: ${CMAKE_INSTALL_PREFIX}")
message(STATUS "=======================================")