# Setup

## 1. Python environment

The project uses its own virtual environment, so it doesn't depend on the system
Python.

```bash
cd ~/forStudy/cam-py
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pins `mediapipe==0.10.21` because newer releases drop the
`mp.solutions.hands` API this project uses. It also pins `numpy<2`, which that
MediaPipe version needs.

Each new terminal needs `source venv/bin/activate` before `python main.py`.
You can also skip activating and run `./venv/bin/python main.py`.

## 2. Virtual camera driver (v4l2loopback)

`pyvirtualcam` writes frames to a fake video device created by the
`v4l2loopback` kernel module. This project expects it at `/dev/video10`.

### Check if it is already loaded

```bash
lsmod | grep v4l2loopback
for d in /sys/class/video4linux/*; do echo "$d: $(cat $d/name)"; done
```

You should see a device such as `video10: ItsGiving`.

### Install and load it

```bash
sudo apt install v4l2loopback-dkms
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="ItsGiving" exclusive_caps=1
```

| Option | Why |
|---|---|
| `video_nr=10` | Creates `/dev/video10`, the default for `--device` |
| `card_label` | The camera name shown in Discord and other apps |
| `exclusive_caps=1` | **Required for Discord, Chrome and other Chromium apps**; without it they do not list the device |

### Load it automatically at boot (optional)

```bash
echo "v4l2loopback" | sudo tee /etc/modules-load.d/v4l2loopback.conf
echo 'options v4l2loopback devices=1 video_nr=10 card_label="ItsGiving" exclusive_caps=1' \
  | sudo tee /etc/modprobe.d/v4l2loopback.conf
```

## 3. Using it in Discord (or Zoom / Meet / OBS)

The order matters:

1. **Free the real webcam.** Only one app can read it at a time. Turn off your
   camera in Discord and close browser tabs that are using it.
2. **Start Hand Cam:** run `python main.py` and wait for
   `Virtual camera running on /dev/video10`.
3. **Pick the camera:** in Discord, go to **User Settings → Voice & Video →
   Camera → ItsGiving**, then click **Test Video**.

With `exclusive_caps=1`, the virtual camera only shows up while something is
writing to it. Start Hand Cam **before** opening the camera list. If it still
doesn't appear, fully quit Discord (including from the tray) and reopen it.

When you quit Hand Cam, Discord shows a black or frozen image until you switch
back to your real webcam.

> Everything drawn on the preview, including the debug overlay and skeleton, is
> also what Discord sees. Press `d` and `l` to hide them for a clean picture.
