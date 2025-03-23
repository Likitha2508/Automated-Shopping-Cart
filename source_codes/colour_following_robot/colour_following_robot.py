import cv2
import numpy as np
from PIL import Image
import RPi.GPIO as GPIO
from time import sleep

# Motor A (Right motor) pins
in1_A = 24
in2_A = 23
en_A = 25

# Motor B (Left motor) pins
in1_B = 17
in2_B = 27
en_B = 22

# GPIO setup
GPIO.setmode(GPIO.BCM)
# Setup Motor A
GPIO.setup(in1_A, GPIO.OUT)
GPIO.setup(in2_A, GPIO.OUT)
GPIO.setup(en_A, GPIO.OUT)
GPIO.output(in1_A, GPIO.LOW)
GPIO.output(in2_A, GPIO.LOW)
# Setup Motor B
GPIO.setup(in1_B, GPIO.OUT)
GPIO.setup(in2_B, GPIO.OUT)
GPIO.setup(en_B, GPIO.OUT)
GPIO.output(in1_B, GPIO.LOW)
GPIO.output(in2_B, GPIO.LOW)

# Setup PWM for both motors with higher initial speed
pA = GPIO.PWM(en_A, 1000)  # Right motor PWM
pB = GPIO.PWM(en_B, 1000)  # Left motor PWM
# Increased initial PWM duty cycle from 50 to 75
pA.start(75)
pB.start(75)

def get_limits(color):
    c = np.uint8([[color]])  # BGR values
    hsvC = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    hue = hsvC[0][0][0]
    
    if hue >= 20 and hue <= 30:  # Yellow range
        lowerLimit = np.array([20, 100, 100], dtype=np.uint8)
        upperLimit = np.array([30, 255, 255], dtype=np.uint8)
    else:
        lowerLimit = np.array([hue - 10, 100, 100], dtype=np.uint8)
        upperLimit = np.array([hue + 10, 255, 255], dtype=np.uint8)
    
    return lowerLimit, upperLimit

def motor_control(left_speed, right_speed):
    """
    Control both motors independently with different speeds
    Speeds can be positive (forward) or negative (backward)
    Range: -100 to 100
    """
    # Add minimum threshold to overcome starting friction
    min_threshold = 40  # Minimum power needed to move the motors
    
    # Only allow forward movement (positive speeds)
    left_speed = max(0, left_speed)
    right_speed = max(0, right_speed)
    
    # Apply minimum threshold for non-zero speeds
    if 0 < left_speed < min_threshold:
        left_speed = min_threshold
    if 0 < right_speed < min_threshold:
        right_speed = min_threshold
    
    # Constrain speeds to valid range
    left_speed = min(left_speed, 100)
    right_speed = min(right_speed, 100)
    
    # Left motor control (only forward movement)
    GPIO.output(in1_B, GPIO.HIGH)
    GPIO.output(in2_B, GPIO.LOW)
    pB.ChangeDutyCycle(left_speed)
    
    # Right motor control (only forward movement)
    GPIO.output(in1_A, GPIO.HIGH)
    GPIO.output(in2_A, GPIO.LOW)
    pA.ChangeDutyCycle(right_speed)

def stop_motors():
    """Stop both motors"""
    pA.ChangeDutyCycle(0)
    pB.ChangeDutyCycle(0)
    GPIO.output(in1_A, GPIO.LOW)
    GPIO.output(in2_A, GPIO.LOW)
    GPIO.output(in1_B, GPIO.LOW)
    GPIO.output(in2_B, GPIO.LOW)

def initialize_camera():
    """Initialize camera with multiple fallback options"""
    for camera_index in [0, 1, 2]:
        cap = cv2.VideoCapture(camera_index)
        if cap.isOpened():
            print(f"Camera initialized with index {camera_index}")
            return cap
        
        gstreamer_str = f'v4l2src device=/dev/video{camera_index} ! video/x-raw,format=BGR ! videoconvert ! appsink'
        cap = cv2.VideoCapture(gstreamer_str, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            print(f"Camera initialized with GStreamer pipeline on device {camera_index}")
            return cap
    
    raise RuntimeError("No camera found. Please check your camera connection and permissions.")

def estimate_distance(bbox, frame_width):
    """Estimate distance based on object size in frame"""
    if bbox is None:
        return float('inf')
    
    x1, y1, x2, y2 = bbox
    object_width = x2 - x1
    reference_width = frame_width / 2  # Width when object is at 50cm
    estimated_distance = (reference_width * 50) / object_width
    
    return estimated_distance

def calculate_motor_speeds(center_error, current_distance):
    """
    Calculate motor speeds based on tracking errors
    center_error: difference from center (-1 to 1, negative means object is left)
    current_distance: current distance from object in cm
    Returns: (left_speed, right_speed)
    """
    TARGET_DISTANCE = 50  # Target distance in cm
    STOP_DISTANCE = 45    # Distance at which to stop (slightly less than target)
    
    # If closer than stop distance, stop both motors
    if current_distance <= STOP_DISTANCE:
        return 0, 0
    
    # Base speed for forward movement
    base_speed = 60
    
    # Turning behavior
    # Negative center_error means object is to the left
    # Positive center_error means object is to the right
    if abs(center_error) > 0.1:  # Add dead zone to prevent small oscillations
        if center_error < 0:  # Object is to the left
            # Right turn: left motor faster, right motor slower
            left_speed = base_speed
            right_speed = base_speed * 0.3  # Significantly reduce inner wheel speed
        else:  # Object is to the right
            # Left turn: right motor faster, left motor slower
            left_speed = base_speed * 0.3  # Significantly reduce inner wheel speed
            right_speed = base_speed
    else:
        # Go straight if object is roughly centered
        left_speed = base_speed
        right_speed = base_speed
    
    return left_speed, right_speed

def main():
    yellow = [255, 0, 0]  # yellow in BGR colorspace
    TARGET_DISTANCE = 50  # Target distance in cm
    
    try:
        cap = initialize_camera()
        
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError("Failed to get first frame")
        
        frame_height, frame_width = frame.shape[:2]
        center_x = frame_width // 2
        print(f"Camera initialized successfully. Frame size: {frame_width}x{frame_height}")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to get frame, retrying...")
                stop_motors()
                sleep(0.1)
                continue

            hsvImage = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            lowerLimit, upperLimit = get_limits(color=yellow)
            mask = cv2.inRange(hsvImage, lowerLimit, upperLimit)
            mask_ = Image.fromarray(mask)
            bbox = mask_.getbbox()

            if bbox is not None:
                x1, y1, x2, y2 = bbox
                frame = cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 5)
                
                # Calculate tracking errors
                object_center_x = (x1 + x2) // 2
                center_error = (object_center_x - center_x) / (frame_width / 2)  # Normalized to [-1, 1]
                
                current_distance = estimate_distance(bbox, frame_width)
                distance_error = current_distance - TARGET_DISTANCE
                
                # Calculate and apply motor speeds
                left_speed, right_speed = calculate_motor_speeds(center_error, distance_error)
                motor_control(left_speed, right_speed)
                
                # Display debugging information
                cv2.putText(frame, f"Distance: {current_distance:.1f}cm", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Center Error: {center_error:.2f}", (10, 70),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                print(f"Distance: {current_distance:.1f}cm, Center Error: {center_error:.2f}")
                print(f"Motor Speeds - Left: {left_speed:.1f}, Right: {right_speed:.1f}")
            else:
                stop_motors()
                print("No object detected")

            cv2.imshow('frame', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\nProgram stopped by user")
    except Exception as e:
        print(f"\nError occurred: {str(e)}")
    finally:
        stop_motors()
        if 'cap' in locals():
            cap.release()
        cv2.destroyAllWindows()
        GPIO.cleanup()

if __name__ == "__main__":
    main()		