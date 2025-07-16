cmake_minimum_required(VERSION 3.16)
project(HFTSystem VERSION 1.0.0 LANGUAGES CXX)

# Set C++ standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build type configuration
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler-specific optimizations
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" OR CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG -march=native -mtune=native")
    set(CMAKE_CXX_FLAGS_DEBUG "-O0 -g3 -DDEBUG")
    
    # Performance optimization flags
    set(PERFORMANCE_FLAGS 
        "-ffast-math"           # Fast floating point math
        "-funroll-loops"        # Unroll loops for performance
        "-finline-functions"    # Inline function calls
        "-fomit-frame-pointer"  # Omit frame pointer for performance
        "-flto"                 # Link-time optimization
        "-fno-rtti"             # Disable RTTI for performance
        "-fno-exceptions"       # Disable exceptions for performance
    )
    
    # SIMD optimization flags
    set(SIMD_FLAGS
        "-mavx2"                # AVX2 instructions
        "-mfma"                 # Fused multiply-add
        "-msse4.2"              # SSE 4.2 instructions
    )
    
    # Memory optimization flags
    set(MEMORY_FLAGS
        "-falign-functions=32"  # Align functions to cache lines
        "-falign-loops=32"      # Align loops to cache lines
        "-fprefetch-loop-arrays" # Prefetch array accesses
    )
    
    # Combine all optimization flags
    string(JOIN " " ALL_OPT_FLAGS ${PERFORMANCE_FLAGS} ${SIMD_FLAGS} ${MEMORY_FLAGS})
    set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} ${ALL_OPT_FLAGS}")
    
    # Profile-guided optimization (PGO) support
    option(ENABLE_PGO "Enable Profile-Guided Optimization" OFF)
    if(ENABLE_PGO)
        set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -fprofile-generate")
        # Note: Second pass would use -fprofile-use
    endif()
endif()

# Platform-specific optimizations
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64")
    add_definitions(-DHFT_X86_64=1)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -m64")
endif()

# Threading support
find_package(Threads REQUIRED)

# OpenMP for parallel processing
find_package(OpenMP)
if(OpenMP_CXX_FOUND)
    add_definitions(-DHFT_OPENMP_ENABLED=1)
endif()

# AWS SDK
find_package(AWSSDK REQUIRED COMPONENTS dynamodb sns cloudwatch secretsmanager)

# DPDK for high-performance networking
find_package(PkgConfig REQUIRED)
pkg_check_modules(DPDK REQUIRED libdpdk)
if(DPDK_FOUND)
    add_definitions(-DHFT_DPDK_ENABLED=1)
endif()

# NUMA support
find_library(NUMA_LIBRARY numa)
if(NUMA_LIBRARY)
    add_definitions(-DHFT_NUMA_ENABLED=1)
endif()

# Machine Learning libraries
find_package(PythonLibs 3.8 REQUIRED)
find_path(EIGEN3_INCLUDE_DIR NAMES signature_of_eigen3_matrix_library PATH_SUFFIXES eigen3)
if(EIGEN3_INCLUDE_DIR)
    add_definitions(-DHFT_EIGEN_ENABLED=1)
endif()

# Google Test for unit testing
find_package(GTest)
find_package(GMock)

# Google Benchmark for performance testing
find_package(benchmark)

# Protobuf for serialization
find_package(Protobuf)
if(Protobuf_FOUND)
    add_definitions(-DHFT_PROTOBUF_ENABLED=1)
endif()

# Include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/core
    ${CMAKE_CURRENT_SOURCE_DIR}/src/strategies
    ${CMAKE_CURRENT_SOURCE_DIR}/src/execution
    ${CMAKE_CURRENT_SOURCE_DIR}/src/data
    ${CMAKE_CURRENT_SOURCE_DIR}/src/risk
    ${CMAKE_CURRENT_SOURCE_DIR}/src/ml
    ${CMAKE_CURRENT_SOURCE_DIR}/src/utils
    ${CMAKE_CURRENT_SOURCE_DIR}/src/fpga
    ${PYTHON_INCLUDE_DIRS}
    ${EIGEN3_INCLUDE_DIR}
)

# Source files organization
set(CORE_SOURCES
    src/core/trading_engine_aws.cpp
    src/core/dpdk_network_engine.cpp
    src/core/market_data_handler_aws.cpp
)

set(STRATEGY_SOURCES
    src/strategies/strategy_manager.cpp
    src/strategies/strategy_factory.cpp
    src/strategies/market_making_strategy.cpp
    src/strategies/mean_reversion_strategy.cpp
    src/strategies/momentum_strategy.cpp
    src/strategies/scalping_strategy.cpp
)

set(EXECUTION_SOURCES
    src/execution/execution_engine.cpp
    src/execution/order_management_system.cpp
)

set(DATA_SOURCES
    src/data/high_performance_order_book.cpp
    src/data/market_data_feed.cpp
    src/data/timestream_client.cpp
)

set(RISK_SOURCES
    src/risk/risk_manager_aws.cpp
)

set(ML_SOURCES
    src/ml/alpha_engine.cpp
)

set(UTILS_SOURCES
    src/utils/numa_memory_manager.cpp
    src/utils/aws_monitoring.cpp
)

set(FPGA_SOURCES
    src/fpga/fpga_interface.cpp
    src/fpga/fpga_risk_engine.cpp
)

set(TESTING_SOURCES
    src/testing/latency_benchmark.cpp
    src/testing/unit_test_framework.cpp
    src/testing/integration_test_suite.cpp
)

# Combine all sources
set(ALL_SOURCES
    ${CORE_SOURCES}
    ${STRATEGY_SOURCES}
    ${EXECUTION_SOURCES}
    ${DATA_SOURCES}
    ${RISK_SOURCES}
    ${ML_SOURCES}
    ${UTILS_SOURCES}
    ${FPGA_SOURCES}
)

# Main HFT System Library
add_library(hft_system STATIC ${ALL_SOURCES})

# Link libraries
target_link_libraries(hft_system
    PUBLIC
    Threads::Threads
    ${AWSSDK_LINK_LIBRARIES}
    ${PYTHON_LIBRARIES}
    ${NUMA_LIBRARY}
)

# Link DPDK if available
if(DPDK_FOUND)
    target_include_directories(hft_system PRIVATE ${DPDK_INCLUDE_DIRS})
    target_link_libraries(hft_system PRIVATE ${DPDK_LIBRARIES})
    target_compile_options(hft_system PRIVATE ${DPDK_CFLAGS_OTHER})
endif()

# Link OpenMP if available
if(OpenMP_CXX_FOUND)
    target_link_libraries(hft_system PUBLIC OpenMP::OpenMP_CXX)
endif()

# Main executable
add_executable(hft_trading_system src/main.cpp)
target_link_libraries(hft_trading_system hft_system)

# Performance benchmark executable
if(benchmark_FOUND)
    add_executable(hft_benchmark src/testing/performance_benchmark.cpp)
    target_link_libraries(hft_benchmark 
        hft_system 
        benchmark::benchmark
    )
endif()

# Unit tests
if(GTest_FOUND AND GMock_FOUND)
    add_executable(hft_unit_tests ${TESTING_SOURCES})
    target_link_libraries(hft_unit_tests
        hft_system
        GTest::gtest_main
        GTest::gmock_main
    )
    
    # Enable testing
    enable_testing()
    add_test(NAME HFTUnitTests COMMAND hft_unit_tests)
    
    # Add custom test target
    add_custom_target(run_tests
        COMMAND ${CMAKE_CTEST_COMMAND} --verbose
        DEPENDS hft_unit_tests
    )
endif()

# Integration tests
add_executable(hft_integration_tests src/testing/integration_test_suite.cpp)
target_link_libraries(hft_integration_tests hft_system)
if(GTest_FOUND)
    target_link_libraries(hft_integration_tests GTest::gtest_main)
endif()

# Latency benchmark
add_executable(hft_latency_benchmark src/testing/latency_benchmark.cpp)
target_link_libraries(hft_latency_benchmark hft_system)

# Code coverage support
option(ENABLE_COVERAGE "Enable code coverage" OFF)
if(ENABLE_COVERAGE)
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" OR CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
        target_compile_options(hft_system PRIVATE --coverage)
        target_link_options(hft_system PRIVATE --coverage)
    endif()
endif()

# Static analysis support
option(ENABLE_STATIC_ANALYSIS "Enable static analysis" OFF)
if(ENABLE_STATIC_ANALYSIS)
    find_program(CLANG_TIDY_EXE NAMES "clang-tidy")
    if(CLANG_TIDY_EXE)
        set_target_properties(hft_system PROPERTIES
            CXX_CLANG_TIDY "${CLANG_TIDY_EXE};-checks=*,-fuchsia-*,-google-*,-zircon-*"
        )
    endif()
    
    find_program(CPPCHECK_EXE NAMES "cppcheck")
    if(CPPCHECK_EXE)
        add_custom_target(cppcheck
            COMMAND ${CPPCHECK_EXE} 
            --enable=all 
            --std=c++20 
            --platform=unix64
            --suppress=missingIncludeSystem
            ${CMAKE_CURRENT_SOURCE_DIR}/src
        )
    endif()
endif()

# Documentation generation
find_package(Doxygen)
if(DOXYGEN_FOUND)
    configure_file(${CMAKE_CURRENT_SOURCE_DIR}/docs/Doxyfile.in 
                   ${CMAKE_CURRENT_BINARY_DIR}/Doxyfile @ONLY)
    
    add_custom_target(docs
        ${DOXYGEN_EXECUTABLE} ${CMAKE_CURRENT_BINARY_DIR}/Doxyfile
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "Generating API documentation with Doxygen"
        VERBATIM
    )
endif()

# Installation configuration
install(TARGETS hft_trading_system
    RUNTIME DESTINATION bin
)

install(TARGETS hft_system
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)

install(DIRECTORY src/
    DESTINATION include/hft
    FILES_MATCHING PATTERN "*.h" PATTERN "*.hpp"
)

# Custom targets for development workflow
add_custom_target(format
    COMMAND find ${CMAKE_CURRENT_SOURCE_DIR}/src -name "*.cpp" -o -name "*.h" | xargs clang-format -i
    COMMENT "Formatting code with clang-format"
)

add_custom_target(quick_test
    COMMAND ${CMAKE_CURRENT_BINARY_DIR}/hft_unit_tests --gtest_filter="*Basic*:*Simple*"
    DEPENDS hft_unit_tests
    COMMENT "Running quick unit tests"
)

add_custom_target(performance_test
    COMMAND ${CMAKE_CURRENT_BINARY_DIR}/hft_latency_benchmark
    DEPENDS hft_latency_benchmark
    COMMENT "Running performance benchmarks"
)

# Package configuration
set(CPACK_PACKAGE_NAME "HFTSystem")
set(CPACK_PACKAGE_VERSION ${PROJECT_VERSION})
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Ultra-Low Latency High-Frequency Trading System")
set(CPACK_PACKAGE_VENDOR "HFT Technologies")
set(CPACK_GENERATOR "TGZ;DEB;RPM")

include(CPack)

# Print configuration summary
message(STATUS "")
message(STATUS "HFT System Build Configuration:")
message(STATUS "  Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "  C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "  Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "  System Processor: ${CMAKE_SYSTEM_PROCESSOR}")
message(STATUS "")
message(STATUS "Feature Support:")
message(STATUS "  DPDK: ${DPDK_FOUND}")
message(STATUS "  NUMA: ${NUMA_LIBRARY}")
message(STATUS "  OpenMP: ${OpenMP_CXX_FOUND}")
message(STATUS "  AWS SDK: ${AWSSDK_FOUND}")
message(STATUS "  Google Test: ${GTest_FOUND}")
message(STATUS "  Google Benchmark: ${benchmark_FOUND}")
message(STATUS "  Protobuf: ${Protobuf_FOUND}")
message(STATUS "  Eigen3: ${EIGEN3_INCLUDE_DIR}")
message(STATUS "")
message(STATUS "Optimization Flags: ${CMAKE_CXX_FLAGS_RELEASE}")
message(STATUS "")