cmake_minimum_required(VERSION 3.14)
project(obi-demo-cpp)

set(CMAKE_CXX_STANDARD 17)

find_library(HIREDIS_LIB hiredis)

add_executable(obi-demo-cpp main.cpp)
target_link_libraries(obi-demo-cpp ${HIREDIS_LIB})
target_include_directories(obi-demo-cpp PRIVATE /usr/local/include)