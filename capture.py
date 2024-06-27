import cv2
import os
import time
def capture_and_save_image(folder_path, student_id):
    # Start the camera
    cap = cv2.VideoCapture(0)

    # Check if the camera opened successfully
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    try:
        # Capture 50 images with a delay
        for i in range(50):
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame.")
                break
            
            # Display the frame count on the image
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(frame, f"Images Captured: {i + 1}/50", (10, 50), font, 1, (255, 255, 255), 2, cv2.LINE_AA)
            
            # Save the frame to specified folder with student_id and count
            img_name = f"{student_id}_{i + 1}.jpg"
            cv2.imwrite(os.path.join(folder_path, img_name), frame)
            
            frame = cv2.resize(frame, (1024,768))
            # Display the resulting frame
            cv2.imshow('Adding New Student', frame)
            
            # Wait for 100 ms and check if 'q' is pressed
            if cv2.waitKey(100) & 0xFF == ord('q'):
                break

            # Optional: Add a delay between captures to control the speed
            time.sleep(0.2)  # Adjust the sleep time as needed

    finally:
        # When everything is done, release the capture and close all windows
        cap.release()
        cv2.destroyAllWindows()