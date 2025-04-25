let
  pkgs = import <nixpkgs> { };
in
pkgs.mkShell {
  packages = [
    (pkgs.python3.withPackages (python-pkgs: [
      python-pkgs.python-dotenv
      python-pkgs.requests
      python-pkgs.google-api-python-client
      python-pkgs.google-auth
    ]))
  ];
}
