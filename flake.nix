{
  description = "Harvest Sheet development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonEnv = pkgs.python3.withPackages (
          python-pkgs: with python-pkgs; [
            python-dotenv
            httpx
            icalendar
            pytz
            python-dateutil
            sqlalchemy
            alembic
            pandas
            tabulate
            rich
            pydantic
            typer
            openpyxl
          ]
        );
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
          ];
        };
      }
    );
}
