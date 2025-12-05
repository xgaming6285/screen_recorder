# Screen Recorder

Lightweight headless screen recorder. Records in MKV format (crash-safe) and auto-splits every hour.

## Requirements

- **FFmpeg** - https://ffmpeg.org/download.html
- **screen-capture-recorder** - https://github.com/rdp/screen-capture-recorder-to-video-windows-free/releases

## Usage

```bash
python recorder_simple.py
```

Or double-click `start_recording.bat`

Press `Ctrl+C` to stop.

## Settings

Edit top of `recorder_simple.py`:

```python
MINUTES_PER_FILE = 60      # Split every hour
FRAMERATE = 30
QUALITY = 23               # Lower = better (18-28)
```

## Output

Files saved to `recordings/` folder as `rec_YYYY-MM-DD_HH-MM-SS.mkv`
