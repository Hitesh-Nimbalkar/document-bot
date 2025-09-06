import requests

# API Gateway endpoint
url = "https://iv99e5q733.execute-api.ap-south-1.amazonaws.com/dev/ingest_data"

# Headers (add API key here if required)
headers = {
    "Content-Type": "application/json"
}

# Request body
payload ={
  "project_id": "demo_project",
  "user_id": "test_user",
  "session_id": "session_12345",
  "s3_bucket": "your-upload-bucket",
  "s3_key": "uploads/tmp/demo_project/test_user/session_12345/sample.pdf",
  "ingest_source": "ui",
  "source_path": "user_given"
}
def call_api():
    try:
        response = requests.post(url, headers=headers, json=payload)
        print("Status Code:", response.status_code)

        # Try to parse JSON response safely
        try:
            print("Response JSON:", response.json())
        except ValueError:
            print("Response Text:", response.text)

    except requests.exceptions.RequestException as e:
        print("Error calling API:", e)

if __name__ == "__main__":
    call_api()
