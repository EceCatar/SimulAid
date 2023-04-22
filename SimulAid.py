import time
import board
import busio
import storage
import sdcardio
import analogio
from yui import Buzz, Button, RGB
import adafruit_ads1x15.ads1115 as ADS
from sensory import Sensory, ContactEvent
from adafruit_ads1x15.analog_in import AnalogIn

# Initialize the I2C bus.
i2c = busio.I2C(board.GP7, board.GP6)

# Initialize the ADS object using the I2C bus.
ads = ADS.ADS1115(i2c, address=0x48)

# Initialize the sensors.
emg_a = AnalogIn(ads, ADS.P0)
emg_b = analogio.AnalogIn(board.A1)

# Initialize the SD storage.
spi = busio.SPI(board.GP10, MOSI=board.GP11, MISO=board.GP12)
cs = board.GP15
sd = sdcardio.SDCard(spi, cs, baudrate = int(1E6))
vfs = storage.VfsFat(sd)

storage.mount(vfs, "/sd")

# Initialize the RGB light.
signal = RGB()

# Initialize the buttons.
start_btn = Button(pins = board.GP20)
capture_btn = Button(pins = board.GP5)
stop_btn = Button(pins = board.GP22)

# Initialize the buzzer.
buzzer = Buzz()

# Initialize the buzz wire and its station.
wire = ContactEvent(ID = "buzz", pins = board.GP0, sample_interval = 1/50)
station = ContactEvent(ID = "station", pins = board.GP1, sample_interval = 1/5)

# Initialize the sensory module.
sensory = Sensory([wire, station])

# Connect the UI elements.
for element in [start_btn, capture_btn, stop_btn, signal, sensory, buzzer]:
    element.connect()

# Set the default state.
state = "init"

# Set signal interval.
signal_interval = 0.1
last_signal_at = 0

# Set export interval.
export_interval = 10
last_export_at = 0

# Initialize an empty buffer.
buffer = []

# Set default values.
waiting = False
file_open = False
run_completed = False
contact_detected = False
run_completed_at = 0
beeped_at = 0

# The waiting time between runs.
waiting_time = 5

def get_voltage(pin):
    return (pin.value * 3.3) / 65536

def write_csv(file, data):
    with open(file, "a") as handle:
        for row in data:
            row = str(row['time']) + "," + str(row['completed']) + "," + str(row['contact']) + "," + str(row['trapezius']) + "," + str(row['deltoid']) + "\n"

            handle.write(row)

def create_csv(file):
    global file_open

    # Check if a file is open or create a new one.
    if file_open:
        return
    else:
        with open(file, "w") as handle:
            handle.write("time,completed,contact,trapezius,deltoid\n")

        file_open = True

while True:
    # Set our RGB to green and wait for the start button.
    if state == "init":
        signal.green()

        # Set default 'finished' values.
        finished = False
        finished_at = 0

        # Listen for the start button being pressed.
        if start_btn.update() and start_btn.value:
            # Initialize a new file.
            file = "/sd/" + str(time.time()) + ".csv"

            # Create a CSV.
            create_csv(file)

            state = "ready"

    if state == "ready":
        signal.blue()

        # Listen for the record button being pressed.
        if start_btn.update() and start_btn.value:
            state = "recording"

        # Listen for the stop button being pressed.
        if stop_btn.update() and stop_btn.value:
            state = "init"

    # Keep looping while the state is 'recording'.
    while state == "recording":
        signal.red()

        # Check if we are finished.
        if last_signal_at - finished_at >= waiting_time and finished:
            state = "init"

            # Remove values from the buffer older than the interval.
            buffer = [item for item in buffer if item['time'] > last_export_at]

            # Write last data to CSV.
            write_csv(file, buffer)

            # Reset the last exported timestamp.
            last_export_at = 0

        # Listen for the capture button being pressed.
        if capture_btn.update() and capture_btn.value:
            run_completed_at = time.monotonic()

        # Sound the buzzer after 5 seconds to indicate the end of the pause.
        if not finished and run_completed and (time.monotonic() - run_completed_at >= waiting_time):
            beeped_at = time.monotonic()

            # Set the buzzer to a different frequency to differentiate from the 'contact' beep.
            buzzer.frequency(1000)

            # Sound the buzzer.
            buzzer.on()

            # Indicate that we are waiting between runs.
            waiting = True

        # Switch the buzzer back off after sounding a short beep.
        if waiting and time.monotonic() - beeped_at >= 0.1:
            buzzer.off()
            buzzer.frequency(500)
            waiting = False

        # Listen for contact on the wire.
        if sensory.sample():
            contact_detected = True
            buzzer.switch(wire.value)

        # Add signal input to the buffer based on our defined interval.
        if time.monotonic() - last_signal_at >= signal_interval:
            # Assign a new timestamp for comparison in the loop.
            last_signal_at = time.monotonic()

            # Append the new values.
            buffer.append({
                'time': time.monotonic(),
                'completed': run_completed,
                'contact': contact_detected,
                'trapezius': get_voltage(emg_a),
                'deltoid': get_voltage(emg_b)
            })

            # Print the last value (Thonny will show this in the plotter).
            print(buffer[-1]['trapezius'], buffer[-1]['deltoid'])

            # Mark the run as completed.
            run_completed = run_completed_at > 0 and (beeped_at - run_completed_at < waiting_time) or finished

            # Set 'contact' back to False.
            contact_detected = False

        # Start exporting to CSV.
        if time.monotonic() - last_export_at >= export_interval and not finished:
            # Remove values from the buffer older than the interval.
            buffer = [item for item in buffer if item['time'] > last_export_at]

            # Assign a new timestamp for comparison with the last export.
            last_export_at = time.monotonic()

            # Write data to CSV.
            write_csv(file, buffer)

        # Listen for the stop button being pressed.
        if stop_btn.update() and stop_btn.value:
            finished = True
            run_completed = True
            file_open = False
            finished_at = time.monotonic()
