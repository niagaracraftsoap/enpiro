cmake_minimum_required(VERSION 3.20)

project(enpiro_native C)

find_package(SQLite3 3.40 REQUIRED)

add_library(enpiro_store STATIC enpiro_store.c enpiro_environment.c)
target_include_directories(enpiro_store PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_features(enpiro_store PUBLIC c_std_11)
target_compile_definitions(enpiro_store PRIVATE _POSIX_C_SOURCE=200809L)
target_compile_options(enpiro_store PRIVATE
    -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
)
target_link_libraries(enpiro_store PUBLIC SQLite::SQLite3 m)

add_executable(enpiro_store_probe store_probe.c)
target_link_libraries(enpiro_store_probe PRIVATE enpiro_store)
target_compile_options(enpiro_store_probe PRIVATE
    -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
)

add_executable(enpiro_record enpiro_record.c)
target_link_libraries(enpiro_record PRIVATE enpiro_store)
target_compile_options(enpiro_record PRIVATE
    -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
)

install(TARGETS enpiro_record RUNTIME DESTINATION bin)

include(CTest)
if(BUILD_TESTING)
    add_executable(enpiro_store_test store_test.c)
    target_link_libraries(enpiro_store_test PRIVATE enpiro_store)
    target_compile_options(enpiro_store_test PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
    )
    add_test(NAME enpiro.native-store COMMAND enpiro_store_test)

    add_executable(enpiro_environment_test environment_test.c)
    target_link_libraries(enpiro_environment_test PRIVATE enpiro_store)
    target_compile_options(enpiro_environment_test PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
    )
    add_test(NAME enpiro.native-environment COMMAND enpiro_environment_test)
endif()
