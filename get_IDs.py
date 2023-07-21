import json

# Function to read the input JSON file and extract required data
def extract_data(input_file):
    with open(input_file, 'r') as f:
        data = json.load(f)

    user_data = {}
    for user in data['collection']:
        permalink = user['permalink']
        user_id = user['id']
        user_data[permalink] = user_id

    return user_data

# Function to create a new JSON file with the extracted data
def save_to_json(output_file, user_data):
    with open(output_file, 'w') as f:
        json.dump(user_data, f, indent=2)

# Main function to execute the script
def main():
    input_file = 'input.json'
    output_file = 'output2.json'

    user_data = extract_data(input_file)
    save_to_json(output_file, user_data)

if __name__ == '__main__':
    main()
