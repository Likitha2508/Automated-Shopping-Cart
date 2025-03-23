import cv2
import numpy as np
import pyzbar.pyzbar as pyzbar
import urllib.request
from bs4 import BeautifulSoup
import re
import serial
import time
from decimal import Decimal

# Function to connect to Arduino
def connect_arduino(port='COM7', baudrate=115200, timeout=.1, max_retries=5):
    retries = 0
    arduino = None
    while retries < max_retries:
        try:
            arduino = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
            print("Connected to Arduino on port:", port)
            break
        except serial.SerialException:
            print(f"Serial port {port} is busy or unavailable. Retrying in 2 seconds...")
            retries += 1
            time.sleep(2)
    return arduino

# Set up serial communication with Arduino
arduino = connect_arduino()

if arduino is None:
    print("Failed to connect to Arduino. Exiting program.")
    exit(1)

# Function to send data to Arduino
def send_to_arduino(items):
    for line in items:  # Sending the data provided in `items`
        arduino.write((line + '\n').encode())
        time.sleep(0.1)

# Function to process URL data and extract name and price
def process_url_data(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        request = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(request)

        # Fetch and parse the HTML content
        html_content = response.read()
        soup = BeautifulSoup(html_content, 'html.parser')

        # Debugging print to inspect page structure
        print("HTML Content fetched from URL:")
        print(soup.prettify())

        # Use flexible search pattern for name and price
        name_tag = soup.find('p', text=re.compile(r"Name:\s*\w+", re.IGNORECASE))
        price_tag = soup.find('p', text=re.compile(r"Price:\s*Rs\.\d+", re.IGNORECASE))

        if name_tag:
            name = re.search(r"Name:\s*(\w+)", name_tag.text, re.IGNORECASE).group(1)
            print(f"Extracted Name: {name}")
        else:
            print("Name not found on page.")
            name = None

        if price_tag:
            price = Decimal(re.search(r"Price:\s*Rs\.(\d+(?:\.\d+)?)", price_tag.text, re.IGNORECASE).group(1))
            print(f"Extracted Price: Rs.{price}")
        else:
            print("Price not found on page.")
            price = None

        return name, price

    except Exception as e:
        print(f"Failed to process URL or extract data: {e}")
        return None, None

# Font and camera URL setup
font = cv2.FONT_HERSHEY_PLAIN
camera_url = 'http://192.168.6.216/capture'

# Variables for scanned items
scanned_items = []
total_price = Decimal('0.00')

# Function to display data on an LCD simulator and send to Arduino
def display_lcd_simulator(names, prices, total_price):
    print("\n" * 5)
    print("20x4 LCD Display Simulation")
    print("Recent Scans:")
    for name, price in zip(names[-3:], prices[-3:]):
        print(f"{name}: Rs.{price:.2f}")
    print(f"Total Price: Rs.{total_price:.2f}")
    display_data = [f"{name}: Rs.{price:.2f}" for name, price in zip(names, prices)]
    display_data.append(f"Total: Rs.{total_price:.2f}")
    send_to_arduino(display_data)

prev = ""
names = []
prices = []
cart_items = []  # Cart will hold a list of tuples with (item_name, item_price)

# Function to handle negative price removal
def handle_negative_price(item_name, item_price):
    global total_price, cart_items, names, prices

    # Find the index of the item in the cart with the matching name and price
    for i in range(len(cart_items) - 1, -1, -1):  # Start from the end
        if cart_items[i] == item_name and prices[i] == abs(item_price):
            # Remove the item and adjust the total price
            total_price -= prices[i]
            names.pop(i)
            prices.pop(i)
            cart_items.pop(i)
            print(f"Removed {item_name} from cart. Adjusted total price: Rs.{total_price:.2f}")
            return  # Exit after removing one item
    print(f"No matching item found for {item_name} with price Rs.{abs(item_price):.2f} to remove.")

# Main processing loop
try:
    while True:
        try:
            # Retrieve and decode the image from the IP camera
            img_resp = urllib.request.urlopen(camera_url)
            imgnp = np.array(bytearray(img_resp.read()), dtype=np.uint8)
            frame = cv2.imdecode(imgnp, -1)

            # Decode QR codes in the frame
            decodedObjects = pyzbar.decode(frame)
            for obj in decodedObjects:
                pres = obj.data.decode('utf-8')
                if prev != pres:
                    print("Type:", obj.type)
                    print("Data:", pres)
                    prev = pres

                    if pres.startswith("http"):
                        # Process as a URL if it starts with "http"
                        name, price = process_url_data(pres)

                        if name and price is not None:
                            if price < 0:  # Handle negative prices
                                handle_negative_price(name, price)
                            else:  # Add positive price items
                                names.append(name)
                                prices.append(price)
                                cart_items.append(name)
                                total_price += price

                            display_lcd_simulator(names, prices, total_price)
                        else:
                            print("Could not find name or price on the page.")

                    else:
                        # Process plain text QR code
                        try:
                            name_match = re.search(r"Name:\s*(\w+)", pres)
                            price_match = re.search(r"Price:\s*Rs\.([+-]?\d+(?:\.\d+)?)", pres)

                            if name_match and price_match:
                                name = name_match.group(1)
                                price = Decimal(price_match.group(1))

                                if price < 0:
                                    handle_negative_price(name, price)
                                else:
                                    names.append(name)
                                    prices.append(price)
                                    cart_items.append(name)
                                    total_price += price

                                display_lcd_simulator(names, prices, total_price)
                            else:
                                print("Invalid QR code format.")
                        except Exception as e:
                            print(f"Error processing plain text QR code data: {e}")

                    # Display the decoded data on the frame
                    cv2.putText(frame, pres, (50, 50), font, 2, (255, 0, 0), 3)

            # Show the live transmission frame
            cv2.imshow("live transmission", frame)

            # Check for ESC key press to break the loop
            if cv2.waitKey(1) & 0xFF == 27:
                break

        except urllib.error.URLError as e:
            print(f"Connection error: {e}")
            break

except KeyboardInterrupt:
    print("Interrupted by user")

finally:
    # Clean up resources
    cv2.destroyAllWindows()
