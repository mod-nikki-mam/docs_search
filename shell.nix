let
  pkgs = import <nixpkgs> { config.allowUnfree = true; };
in
pkgs.mkShell {
  packages = with pkgs; [
    (python313.withPackages (
      p: with p; [
        qdrant-client
        gitpython
        textual
        textual-dev
        ipython
        fastembed
        docker
        uvicorn
        fastapi
        pydantic
        sqlalchemy
        asyncpg
        jinja2
        python-multipart
      ]
    ))
  ];
}
