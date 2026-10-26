# Cython Breeze bindings

This project exposes every C API function in `breeze.h` through the importable
`breeze` extension module. The C++ implementation (and compiled shared library)
is **not** provided: compile the upstream Breeze project to `libbreeze.so`
(Linux), `libbreeze.dylib` (macOS), or `breeze.lib` + `breeze.dll` (Windows).

## Build

Run these commands from the directory containing `setup.py`:

```bash
python -m pip install -U pip
# Set these to the actual directories containing breeze.h and the Breeze library:
export BREEZE_INCLUDE_DIR=/path/to/include
export BREEZE_LIB_DIR=/path/to/lib
python -m pip install .
```

On Windows (PowerShell):

```powershell
$env:BREEZE_INCLUDE_DIR = 'C:\path\to\include'
$env:BREEZE_LIB_DIR = 'C:\path\to\lib'
py -m pip install .
```

The Breeze DLL must also be visible to the Windows loader (e.g. by putting its
directory on PATH before starting Python). On Linux/macOS ensure the library's
transitive dependencies can be found by the dynamic loader; the setup script
sets a runtime library search path to `BREEZE_LIB_DIR` on those platforms.

## Example

```python
from breeze import BreezeWrapper, BreezeRequest, last_error

request = BreezeRequest(
    text="Hello from Breeze!",
    instruction="Speak calmly",
    seed=42,
    max_new_tokens=0,
)

with BreezeWrapper("/path/to/model.gguf", use_gpu=False) as breeze:
    print("Sample rate:", breeze.sample_rate())
    breeze.generate_wav(request, "output.wav")

    audio_samples = []
    breeze.generate(request, lambda chunk: audio_samples.extend(chunk))
    # callback(chunk) is called with a Python list of floating-point samples;
    # return a truthy value to request that generation stop.

    # Saved voice codes must be a FLAT iterable of C int values with exactly
    # frames * n_codebooks entries, in the layout expected by the native API:
    frames, n_codebooks = 10, 8  # replace with dimensions of your codes
    codes = [0] * (frames * n_codebooks)  # replace with real codes
    # breeze.generate_voice_wav(request, codes, frames, n_codebooks, "voice.wav")
    # breeze.generate_voice(request, codes, frames, n_codebooks, callback)
    # breeze.decode_voice_wav(codes, frames, n_codebooks, "decoded.wav")

print(last_error())
```

All request fields are exposed by `BreezeRequest`: `text`, `instruction`,
`ref_text`, `ref_audio`, `cfg_scale`, `seed`, `max_new_tokens`, `split_chars`,
`temperature`, `top_k`, `top_p`, and `repetition_penalty`. Optional pointers
become NULL when the corresponding Python argument is `None`. `ref_audio`
uses mono 24-kHz floating-point samples. The request's numeric defaults in
this wrapper are zero; tune them for your model and desired synthesis.

Methods map one-to-one onto native functions: constructor → `breeze_init`,
`close` → `breeze_free`, `sample_rate`, `generate`, `generate_wav`,
`last_error`, `generate_voice`, `generate_voice_wav`, and `decode_voice_wav`.
Native nonzero generation return codes raise `RuntimeError`; callback Python
exceptions are propagated. Calls are synchronous; do not concurrently close
an instance while a generation call is running.

## Saved voice files (`.breeze`)

`read_voice(path)` reads the upstream BRZV version-1 binary format without
loading a model. It returns `(codes, n_codebooks, transcript)` where `codes`
is a flat frame-major list of signed little-endian int32 values. Compute the
frame count as `len(codes) // n_codebooks`.

```python
from breeze import BreezeWrapper, BreezeRequest, read_voice, load_voice

codes, n_codebooks, transcript = read_voice("voices/harbour.breeze")
frames = len(codes) // n_codebooks

with BreezeWrapper("model.gguf", use_gpu=True) as breeze:
    request = BreezeRequest(text="Hello again!", ref_text=transcript)
    breeze.generate_voice_wav(request, codes, frames, n_codebooks, "output.wav")

# For additional metadata:
voice = load_voice("voices/harbour.breeze")
print(voice.frames, voice.sample_rate)
```

Only BRZV format version 1 is supported. The loader validates the magic,
version, dimensions, file length and UTF-8 transcript. Saved codes are tied to
the codec/model used to create them; dimensions alone cannot prove compatibility.

Note that the methods `generate_voice` and `generate_voice_wav` require a modified version of the upstream breeze.cpp source code (not included in the current build).