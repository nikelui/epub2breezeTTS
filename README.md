# epub2breezeTTS

A collection of tools for building a pipeline ebook -> audiobook in Pyhton using Breeze-TTS2 for voice synthesis.

## Dependencies
- pysbd
- beautifulsoup4
- lxml
- requests
- ffmpeg
- ebooklib >= 0.20  # Older versions have a bug with Windows paths

## Setup
- The project uses [pixi](https://pixi.prefix.dev/latest/) for package management. If you use another tool you need to recreate the command-line tasks defined in pixi.toml yourself.
- The TTS engine is based on [Breeze-TTS-2.cpp](https://github.com/HoppouAI/Breeze-TTS-2.cpp).
In *breeze_native* are the compiled C++ libraries and tools (Linux only), while *breeze_python* contains the Cython wrapper that is used by the main program.
  - The breeze.cpp library has been slightly modified to include the ability to pass a pre-saved voice file (voice.breeze format) instead of a reference audio .wav and audio transcript. I might include the source code or static libraries of this breeze.cpp version in future updates.
- As a fallback for other platforms, there is an implementation of the breeze-server http backend. You need to separately download breeze.cpp binaries for your platform and start a server (follow the breeze.cpp documentation). You can then change the configuration options to use the http backend.
## Instructions

**~Coming Soon**

## How to use
`epub2breeze [command] [--options]`

**Recommended**: invoke the command from the root folder with `pixi run epub2breeze ...` to run the application.  
In alternative, you need to first install the command using `pip install` or `pyinstaller`.

#### Global options
> `--config`: Path to the application configuration file (default: "config/config.json"). Most of the command-line options can be included in the configuration file.

**Options priority**: Command-line > config.json > program defaults.

### Commands
#### Text processing
`process_text [epub] [--options]`

Process EPUB, extract the metadata and text, and chunk the chapters paragraphs in short sentences for audio generation.
The intermediate output is saved to *output-dir*.

#### Options
> `epub`: Path to the EPUB file to process  
> `--output-dir`: Output directory for processed text  
> `--max-chars`: Maximum characters per chunk. Default: 400  
> `--target-chars`: Target characters per chunk. Default: 300  
> `--min-chars`: Minimum characters per chunk. Default: 150  
> `--verbose`: Print book metadata, number of chapters, paragraphs and number of chunks.  
> `--book-structure`: Print content of epub spine and table of content, then exit.  

#### Information
`info [--options]`

Print information about an already processed ebook. Shows book metadata, list of chapters including chapter title, lenght and number of chunks.
#### Options
> `--output-dir`: Output directory containing processed book data.  
> `--chunks`: In addition, lists every chunk and its status (processed, pending, failed). **Note**: the output can be extremely long, it's reccomended to filter the stdout or redirect to file.

#### Generate Audio
`audio_synthesis [--options]`

Reads the chunks of text generated in the previous step and generate audio narration using Breeze.cpp.  
You can use either the Breeze Cython-wrapped C++ library (Linux only for now), otherwise you need to start a separate `breeze-server` process (instructions in the [breeze.cpp](https://github.com/HoppouAI/Breeze-TTS-2.cpp) repository) and use the http backend to communicate with it.  
The breeze executable needs the model weights, downloaded from HuggingFace ([link](https://huggingface.co/HoppouAI/Breeze-TTS-2.cpp)).  
Voices can be pre-encoded to a *voice.breeze* file for convenience, using the breeze-cli application from breeze.cpp (refer to the project documentation). Make sure to use the same model weights used to encode the voice file, otherwise the generated tone and pitch might differ.

#### Options
> `--backend`: Backend to use for audio synthesis. Choices: "cython", "http"  
> `--output-dir`: Output directory for generated audio files. It should point to the directory containing *chunks.jsonl*. The intermediate .wav files are saved to *output-dir/audio*, with a separate sub-folder for each chapter. Default: "output/"  
> `--model`: Path to the Breeze GGUF model weights file.   
> `--reference-wav`: Path to a reference .wav audio for voice cloning.  
> `--reference-text`: Path to a text file with the exact transcript of *reference-wav*.  
> `--voice-dir`: Path to the saved voices directory. Default: "voices/"  
> `--voice-id`: ID of a pre-encoded voice, contained in *voice-dir*. 
> `--chapters`: Expression of the ebook chapters to process (e.g. “1,3-5”). Default: None (process all chapters).  
> `--chapter-intro`: Generate a spoken chapter heading (E.g. "Chapter 1"). Useful if the text has unconventional chapter titles. For more information and configuration, see "config-only options". Default: None.  
> `--cfg-scale`: Configuration scale. Default: 1.0  
> `--seed`: Random seed for reproducibility. Default: 42  
> `--cpu`: Use CPU instead of GPU. Default: false  
> `--force`: Regenerate selected WAVs. Default: false  
> `--retry-failed`: Retry failed audio generation attempts. Default: true

#### Assemble Audiobook
`assemble_audiobook [--options]`

Assemble the individual chunk.wav audio files into full chapters.

#### Options
> `--output-dir`: Output directory for assembled audiobook. It should point to the directory containing chunks.jsonl and the audio/ folder. Default: "output/"  
`--pause-config`: JSON file containing silence durations by ending type. For more information see "config-only options". Default: "config/assembly_pauses.json"  
`--format`: Output format. Choices: "mp3", "m4b". **Note**: mp3 files are best used for individual chapters, they might not support chapter bookmarks and other metadata like m4b.  
`--bitrate`: Audio bitrate. Default: "128k"  
`--ffmpeg`: Path to ffmpeg executable, works best if included in PATH. Default: "ffmpeg"  
`--ffprobe`: Path to ffprobe executable, works best if included in PATH. Default: "ffprobe"  
`--overwrite`: Overwrite existing files. Default: false  
`--intro`: Include artificial chapter headings generated in the previous step. Default: true  
`--chapters`: Expression with chapters to include in the audiobook (e.g. "2,3,4-7"). Default: None (include all chapters).  
`--combine`: Combine individual M4B chapters into a single bookmarked audiobook. Default: false  
`--combine-chapters`: Expression with chapters to include in the combined audiobook (if true), e.g. "1-3,5". Default: None (include all chapters).

### Config-only options
**~Coming soon**
