{
  description = "elder's ears: tools for reading (and later making) music with my hands";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  outputs = { nixpkgs, ... }:
    let
      systems = [ "aarch64-darwin" "x86_64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in {
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [ python312 uv ffmpeg yt-dlp aubio fluidsynth soundfont-fluid sox ];
          shellHook = ''
            export UV_PYTHON=${pkgs.python312}/bin/python3
            export SOUNDFONT=${pkgs.soundfont-fluid}/share/soundfonts/FluidR3_GM2-2.sf2
          '';
        };
      });
    };
}
