# cython: language_level=3, boundscheck=False, wraparound=False
"""Cython bindings to the C ABI exposed by breeze.h."""
from array import array

cdef extern from "breeze.h":
    ctypedef struct breeze_context:
        pass
    ctypedef int (*breeze_audio_cb)(const float *, int, void *)
    ctypedef struct breeze_request:
        const char *text
        const char *instruction
        const char *ref_text
        const float *ref_audio
        int ref_audio_len
        float cfg_scale
        int seed
        int max_new_tokens
        int split_chars
        float temperature
        int top_k
        float top_p
        float repetition_penalty

    breeze_context *breeze_init(const char *, int)
    void breeze_free(breeze_context *)
    int breeze_sample_rate(breeze_context *)
    int breeze_generate(breeze_context *, const breeze_request *, breeze_audio_cb, void *)
    int breeze_generate_wav(breeze_context *, const breeze_request *, const char *)
    const char *breeze_last_error()
    int breeze_generate_voice(breeze_context *, const breeze_request *, const int *, int, int, breeze_audio_cb, void *)
    int breeze_generate_voice_wav(breeze_context *, const breeze_request *, const int *, int, int, const char *)
    int breeze_decode_voice_wav(breeze_context *, const int *, int, int, const char *)


def last_error():
    """Return the native library's last error message (if any)."""
    cdef const char *msg = breeze_last_error()
    return msg.decode("utf-8", "replace") if msg != NULL else ""


class BreezeRequest:
    """Options corresponding exactly to the fields of C breeze_request.

    ref_audio, when provided, contains mono 24 kHz float samples.
    """
    def __init__(self, text, instruction=None, ref_text=None, ref_audio=None,
                 cfg_scale=0.0, seed=0, max_new_tokens=0, split_chars=0,
                 temperature=0.0, top_k=0, top_p=0.0,
                 repetition_penalty=0.0):
        self.text = text
        self.instruction = instruction
        self.ref_text = ref_text
        self.ref_audio = ref_audio
        self.cfg_scale = cfg_scale
        self.seed = seed
        self.max_new_tokens = max_new_tokens
        self.split_chars = split_chars
        self.temperature = temperature
        self.top_k = top_k
        self.top_p = top_p
        self.repetition_penalty = repetition_penalty


cdef class _PreparedRequest:
    cdef breeze_request native
    cdef object text_buf, instruction_buf, ref_text_buf, ref_audio_buf
    cdef float[::1] audio_view

    def __cinit__(self):
        self.native.text = NULL
        self.native.instruction = NULL
        self.native.ref_text = NULL
        self.native.ref_audio = NULL
        self.native.ref_audio_len = 0

    def __init__(self, request):
        if not isinstance(request, BreezeRequest):
            raise TypeError("request must be a BreezeRequest")
        self.text_buf = str(request.text).encode("utf-8")
        self.native.text = self.text_buf
        if request.instruction is not None:
            self.instruction_buf = str(request.instruction).encode("utf-8")
            self.native.instruction = self.instruction_buf
        if request.ref_text is not None:
            self.ref_text_buf = str(request.ref_text).encode("utf-8")
            self.native.ref_text = self.ref_text_buf
        if request.ref_audio is not None:
            self.ref_audio_buf = array('f', request.ref_audio)
            self.audio_view = self.ref_audio_buf
            self.native.ref_audio_len = len(self.ref_audio_buf)
            if self.native.ref_audio_len:
                self.native.ref_audio = &self.audio_view[0]
        self.native.cfg_scale = request.cfg_scale
        self.native.seed = request.seed
        self.native.max_new_tokens = request.max_new_tokens
        self.native.split_chars = request.split_chars
        self.native.temperature = request.temperature
        self.native.top_k = request.top_k
        self.native.top_p = request.top_p
        self.native.repetition_penalty = request.repetition_penalty


cdef class _Codes:
    cdef object buf
    cdef int[::1] view
    cdef const int *ptr

    def __cinit__(self):
        self.ptr = NULL

    def __init__(self, codes, int frames, int n_codebooks):
        if frames <= 0 or n_codebooks <= 0:
            raise ValueError("frames and n_codebooks must be positive")
        if sizeof(int) != array('i').itemsize:
            raise RuntimeError("platform array('i') size differs from C int")
        self.buf = array('i', codes)
        if len(self.buf) != frames * n_codebooks:
            raise ValueError("codes must contain frames * n_codebooks integers")
        self.view = self.buf
        self.ptr = &self.view[0]


cdef class _CallbackState:
    cdef object callback
    cdef object error
    def __init__(self, callback):
        if not callable(callback):
            raise TypeError("callback must be callable")
        self.callback = callback
        self.error = None


cdef int _audio_callback(const float *samples, int n_samples, void *user) noexcept with gil:
    cdef _CallbackState state = <_CallbackState><object>user
    cdef int i
    try:
        # Callback receives a Python list of float samples. Return nonzero to stop.
        return 1 if state.callback([samples[i] for i in range(n_samples)]) else 0
    except BaseException as exc:
        state.error = exc
        return 1


cdef void _check(int rc):
    if rc != 0:
        raise RuntimeError(last_error() or f"Breeze returned error code {rc}")


cdef class BreezeWrapper:
    """Own a native breeze_context. Close explicitly or use a 'with' block.

    The underlying library must remain loaded and calls must finish before close().
    """
    cdef breeze_context *ctx

    def __cinit__(self):
        self.ctx = NULL

    def __init__(self, gguf_path, use_gpu=False):
        cdef bytes path = str(gguf_path).encode("utf-8")
        self.ctx = breeze_init(path, int(bool(use_gpu)))
        if self.ctx == NULL:
            raise RuntimeError(last_error() or "breeze_init failed")

    def __dealloc__(self):
        if self.ctx != NULL:
            breeze_free(self.ctx)
            self.ctx = NULL

    def close(self):
        """Call breeze_free; safe to call repeatedly."""
        if self.ctx != NULL:
            breeze_free(self.ctx)
            self.ctx = NULL

    def __enter__(self):
        self._require_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    cdef void _require_open(self):
        if self.ctx == NULL:
            raise RuntimeError("BreezeWrapper is closed")

    def sample_rate(self):
        """Call breeze_sample_rate."""
        self._require_open()
        return breeze_sample_rate(self.ctx)

    def last_error(self):
        """Call breeze_last_error (global library error state)."""
        return last_error()

    def generate(self, request, callback):
        """Call breeze_generate; callback(samples) returns truthy to stop."""
        self._require_open()
        cdef _PreparedRequest req = _PreparedRequest(request)
        cdef _CallbackState state = _CallbackState(callback)
        cdef int rc = breeze_generate(self.ctx, &req.native, _audio_callback, <void *><object>state)
        if state.error is not None:
            raise state.error
        _check(rc)

    def generate_wav(self, request, out_path):
        """Call breeze_generate_wav, writing 16-bit PCM WAV."""
        self._require_open()
        cdef _PreparedRequest req = _PreparedRequest(request)
        cdef bytes path = str(out_path).encode("utf-8")
        _check(breeze_generate_wav(self.ctx, &req.native, path))

    def generate_voice(self, request, codes, frames, n_codebooks, callback):
        """Call breeze_generate_voice with flat frame/codebook codes."""
        self._require_open()
        cdef _PreparedRequest req = _PreparedRequest(request)
        cdef _Codes packed = _Codes(codes, frames, n_codebooks)
        cdef _CallbackState state = _CallbackState(callback)
        cdef int rc = breeze_generate_voice(self.ctx, &req.native, packed.ptr,
                                            frames, n_codebooks,
                                            _audio_callback, <void *><object>state)
        if state.error is not None:
            raise state.error
        _check(rc)

    def generate_voice_wav(self, request, codes, frames, n_codebooks, out_path):
        """Call breeze_generate_voice_wav."""
        self._require_open()
        cdef _PreparedRequest req = _PreparedRequest(request)
        cdef _Codes packed = _Codes(codes, frames, n_codebooks)
        cdef bytes path = str(out_path).encode("utf-8")
        _check(breeze_generate_voice_wav(self.ctx, &req.native, packed.ptr,
                                         frames, n_codebooks, path))

    def decode_voice_wav(self, codes, frames, n_codebooks, out_path):
        """Call breeze_decode_voice_wav."""
        self._require_open()
        cdef _Codes packed = _Codes(codes, frames, n_codebooks)
        cdef bytes path = str(out_path).encode("utf-8")
        _check(breeze_decode_voice_wav(self.ctx, packed.ptr, frames,
                                       n_codebooks, path))


def read_voice(path):
    """Read a .breeze file and return (codes, n_codebooks, transcript)."""
    from breeze_voice import read_voice as _read_voice
    return _read_voice(path)


def load_voice(path):
    """Read a .breeze file including frames and sample_rate metadata."""
    from breeze_voice import load_voice as _load_voice
    return _load_voice(path)
