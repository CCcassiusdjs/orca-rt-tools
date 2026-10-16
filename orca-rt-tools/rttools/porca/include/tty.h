#include <string>
#include <iostream>

namespace tty {

  class tty_style {
    private:
      std::string code;

    public:
      tty_style(std::string c);
      friend tty_style operator+(const tty_style& s, const tty_style& t);
      friend std::ostream& operator<<(std::ostream& os, const tty::tty_style& style);
  };
  
  const tty::tty_style black   ( "30" );
  const tty::tty_style red     ( "31" );
  const tty::tty_style green   ( "32" );
  const tty::tty_style yellow  ( "33" );
  const tty::tty_style blue    ( "34" );
  const tty::tty_style magenta ( "35" );
  const tty::tty_style cyan    ( "36" );
  const tty::tty_style white   ( "37" );

  const tty::tty_style b_black   ( "40" );
  const tty::tty_style b_red     ( "41" );
  const tty::tty_style b_green   ( "42" );
  const tty::tty_style b_yellow  ( "43" );
  const tty::tty_style b_blue    ( "44" );
  const tty::tty_style b_magenta ( "45" );
  const tty::tty_style b_cyan    ( "46" );
  const tty::tty_style b_white   ( "47" );

  const tty::tty_style a_reset   ( "0"  );
  const tty::tty_style a_bold    ( "1"  );
  const tty::tty_style a_ul      ( "4"  );
  const tty::tty_style a_inv     ( "7"  );
  const tty::tty_style u_bold    ( "21" );
  const tty::tty_style u_ul      ( "24" );
  const tty::tty_style u_inv     ( "27" );
}
