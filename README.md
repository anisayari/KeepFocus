# Keep Focus!

> Stop scrolling or I will start tamtam!

Cross-platform tool for macOS and Windows that tracks your gaze with the webcam 👀:

- when you look at the screen, the video pauses and stays hidden 🛑
- when you look at your phone, the video stays hidden 📱
- when you genuinely look away, a smaller top-left video panel slides in and starts with sound 🥁
- calibration can play a sound and speak on macOS to tell you when to switch target 🔊
- after each calibration announcement, there is a short repositioning delay before capture starts ⏱️
- calibration now captures more samples for each target 📊
- gaze detection is smoothed over time and stabilized across several frames for better robustness 🧱
- calibration now also models face distance and is more tolerant to small screen angle changes 📏
- during calibration, a stability score is shown live ✅
- after calibration, a verification pass gives you a final score and a clear check result 🎯
- right after calibration, one panel shows the average `screen` and `phone` values used by the classifier 📈
- a second diagnostics panel shows how well calibration samples separate around the decision boundary 🧠

## 🍎 Run on macOS

Double-click [run_mac.command](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/run_mac.command) or run:

```bash
./run_mac.command
```

The script:

- creates `.venv` if needed
- installs dependencies
- opens the webcam in a larger window
- loads the local video
- asks whether you want to calibrate at startup

## 🪟 Run on Windows

Double-click [run_windows.bat](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/run_windows.bat).

Compatibility note: [lancer.bat](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/lancer.bat) still works and simply forwards to `run_windows.bat`.

The Windows script:

- creates `.venv` if needed
- installs dependencies
- launches `main.py`
- prints Python errors before closing

## ⌨️ Shortcuts

- `C` at startup: start calibration
- `S` / `Enter` / `Space`: continue with the saved calibration or without calibration
- `C` during tracking: recalibrate
- `Q` or `ESC`: quit

## 📁 Useful Files

- [main.py](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/main.py): webcam logic, gaze detection, calibration, player control
- [video_player.html](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/video_player.html): video window
- [videos/youtube_trigger_video.mp4](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/videos/youtube_trigger_video.mp4): video clip played when you look away
- [models/face_landmarker.task](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/models/face_landmarker.task): MediaPipe model
- [run_mac.command](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/run_mac.command): macOS launcher
- [run_windows.bat](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/run_windows.bat): Windows launcher

## 📝 Notes

- Chrome is preferred on macOS for the video player.
- Chrome or Edge works on Windows.
- The calibration profile is saved in `attention_calibration.json`.
- If an older saved calibration becomes incompatible with the newer classifier, the app will ask you to recalibrate.
- The video window comes to the front when the state becomes `away`.
- On macOS, the video window is hidden again when the state returns to `screen` or `phone`.
