# Spinphony
![alt text](model.png)
ECE 3140 final project by Ibrahim Ahmed, Geneustace Wicaksono, and Ibrahim Alyamani.

Spinphony turns computer audio into live motor music using an STFT-based host pipeline, an FRDM-KL46Z microcontroller, DRV8825 stepper drivers, and four NEMA17 motors coupled to resonance chambers.

## Links

- Project webpage: https://sentientplatypus.github.io/spinphony/
- Demo/sample playlist: https://www.youtube.com/playlist?list=PL1kjgJJbafhrtG4_A-ouzDBUkkYVFYieY


## STFT on laptop

### Structure

- `main.py` captures system audio, runs the STFT, shows the live UI, and streams motor frames over serial.
- `audio_input.py` samples audio from the computer.
- `stft.py` detects notes and maps them to four motor frequency tracks.
- `live_ui.py` displays the live spectrum and motor frequencies.
- `motor_serial.py` formats and sends serial packets to the microcontroller.

### How to run

1. Install Python dependencies:

   ```sh
   pip install numpy soundcard pyserial
   ```

2. Install/configure a virtual audio cable such as VB-CABLE then route the app/browser audio to the cable input.
3. Set `DEFAULT_SERIAL_PORT` in `main.py` to the microcontroller port, if needed.
4. Run:

   ```sh
   python main.py
   ```

## Embedded firmware

### Structure

- `main.c` starts the embedded app.
- `app.c` initializes board, motor driver, serial stream, and main service loop.
- `motor.c` drives four stepper motors from timer interrupts.
- `serial_stream.c` receives UART/DMA packets from the Python host.
- `constants.h` sets all parameters.

### How to run

1. Copy the entire MKL46Z4_Project_FINALPROJECT project or copy the files in MKL46Z4_Project_FINALPROJECT/source into a project's source directory
2. Build and flash the project to the FRDM-KL46Z.
3. Connect the board over serial at `230400` baud; the Python host will stream 20-byte motor frames to it.
