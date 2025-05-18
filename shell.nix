let
  pkgs = import <nixpkgs> { };
in
pkgs.mkShell {
  packages = [
    (pkgs.python3.withPackages (python-pkgs: [
      python-pkgs.google-api-python-client
      python-pkgs.google-auth
      python-pkgs.google-auth-oauthlib
      python-pkgs.gspread
      python-pkgs.pandas
      python-pkgs.pydantic
      python-pkgs.python-dateutil
      python-pkgs.python-dotenv
      python-pkgs.requests
      python-pkgs.rich
    ]))
  ];
}
