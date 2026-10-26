# epub2breezeTTS

A collection of tools for building a pipeline ebook -> audiobook in Pyhton using Breeze-TTS2 for voice synthesis.

## Dependencies
- pysbd
- beautifulsoup4
- lxml
- requests
- ffmpeg
- ebooklib >= 0.20  # Older versions have a bug with Windows

## Setup
- The project uses [pixi](https://pixi.prefix.dev/latest/) for package management. If you use another tool you need to recreate the command-line tasks defined in pixi.toml yourself.
- The TTS engine is based on [Breeze-TTS-2.cpp](https://github.com/HoppouAI/Breeze-TTS-2.cpp).
In *breeze_native* are the compiled C++ libraries and tools (Linux only), while *breeze_python* contains the Cython wrapper that is used by the main program.
  - The breeze.cpp library has been slightly modified to include the ability to pass a pre-saved voice file (voice.breeze format) instead of a reference audio .wav and audio transcript. I might include the source code or static libraries of this breeze.cpp version in future updates.
- As a fallback for other platforms, there is an implementation of the breeze-server http backend. You need to separately download breeze.cpp binaries for your platform and start a server (follow the breeze.cpp documentation). You can then change the configuration options to use the http backend.
## Instructions

**Coming Soon**
