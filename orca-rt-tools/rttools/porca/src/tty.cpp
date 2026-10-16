#include "../include/tty.h"

namespace tty {

tty_style::tty_style(std::string c){
    this->code = c;
}

tty::tty_style operator+(const tty_style& s, const tty_style& t){
    return tty_style(s.code + ";" + t.code);
}

std::ostream& operator<<(std::ostream& os, const tty::tty_style& style){
    #ifndef NO_TTY_COLORS
    return (os << "\033[" << style.code << "m");
    #else
    return os;
    #endif
}

}