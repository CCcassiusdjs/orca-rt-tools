#include <iostream>
#include <map>
#include <vector>

#include "../include/main.h"
#include "../include/tty.h"

int main(int argc, char** argv){
  
  std::map<std::string, std::string> params;

  // prints the orca whale logo and welcome message 
  for(const auto& s: WELCOME_MESSAGE)
    std::cout << (tty::white + tty::b_blue + tty::a_bold) << s << tty::a_reset << std::endl;

  // parse parameters values into a dictionary
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
      if (arg.substr(0, 1) == "-") {
          std::string key = arg.substr(1);
          std::string value = (i + 1 < argc && argv[i + 1][0] != '-') ? argv[i + 1] : "";
          params[key] = value;
      }
  }

  for (const auto& kvp : params)
    std::cout << "Key: " << kvp.first << ", Value: " << kvp.second << std::endl;

}