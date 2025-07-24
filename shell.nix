{
  system ? builtins.currentSystem,
}:
let
  pins = import ./npins { };
  pkgs = import pins.nixpkgs { inherit system; };

  pythonWithPackages = pkgs.python3.withPackages (
    ps: with ps; [
      google-api-python-client
      google-auth
      google-auth-oauthlib
      gspread
      pandas
      pydantic
      python-dateutil
      python-dotenv
      requests
      rich
    ]
  );
in
pkgs.mkShell {
  buildInputs = [ pythonWithPackages ];
}
