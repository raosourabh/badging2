import boto3
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

YOUR_REGION = os.getenv('AWS_REGION', 'us-east-1')

dynamodb = boto3.resource('dynamodb', region_name=YOUR_REGION)

chat_table = dynamodb.Table('ChatHistory')
slot_bookings_table = dynamodb.Table('SlotBookings')
conversation_log_table = dynamodb.Table('ConversationLog')

@app.route('/api/save-slot', methods=['POST'])
def save_slot():
    try:
        data = request.json
        item = {
            'id': str(uuid.uuid4()),
            'amazonId': data['email'],
            'slot': data['slot'],
            'site': data['site'],
            'type': data['type'],
            'timestamp': datetime.now().isoformat()
        }
        slot_bookings_table.put_item(Item=item)
        return jsonify({'success': True, 'item': item})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/slots', methods=['GET'])
def get_slots():
    try:
        response = slot_bookings_table.scan()
        return jsonify(response['Items'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversation/start', methods=['POST'])
def start_conversation():
    try:
        data = request.json
        conversation_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        
        item = {
            'conversationId': conversation_id,
            'sessionId': session_id,
            'userEmail': data['userEmail'],
            'startTime': datetime.now().isoformat(),
            'messages': []
        }
        chat_table.put_item(Item=item)
        
        first_row = {
            'id': str(uuid.uuid4()),
            'conversationId': conversation_id,
            'amazonId': data['userEmail'],
            'user': '',
            'bot': '',
            'timestamp': datetime.now().isoformat(),
            'messageOrder': 0
        }
        conversation_log_table.put_item(Item=first_row)
        
        return jsonify({
            'conversationId': conversation_id,
            'sessionId': session_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/message', methods=['POST'])
def save_message():
    try:
        data = request.json
        
        response = conversation_log_table.scan(
            FilterExpression='conversationId = :cid',
            ExpressionAttributeValues={':cid': data['conversationId']}
        )
        message_order = len(response['Items'])
        
        message_item = {
            'id': str(uuid.uuid4()),
            'conversationId': data['conversationId'],
            'amazonId': '',
            'user': data['message'] if data['sender'] == 'user' else '',
            'bot': data['message'] if data['sender'] == 'bot' else '',
            'timestamp': datetime.now().isoformat(),
            'messageOrder': message_order
        }
        
        conversation_log_table.put_item(Item=message_item)
        return jsonify({'success': True, 'message': message_item})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversation/end', methods=['POST'])
def end_conversation():
    try:
        data = request.json
        chat_table.update_item(
            Key={'conversationId': data['conversationId']},
            UpdateExpression='SET endTime = :endTime',
            ExpressionAttributeValues={':endTime': datetime.now().isoformat()}
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/setup', methods=['GET'])
def setup_page():
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Setup Tables</title></head>
    <body>
        <h2>DynamoDB Table Management</h2>
        <button onclick="deleteTables()" style="background-color: #ff4444;">Delete Old Tables</button>
        <button onclick="createTables()" style="background-color: #44ff44;">Create New Tables</button>
        <div id="result"></div>
        <script>
        function deleteTables() {
            fetch('/delete/tables', {method: 'POST'})
            .then(response => response.json())
            .then(data => {
                document.getElementById('result').innerHTML = 
                    '<h3>Delete Result:</h3><pre>' + JSON.stringify(data, null, 2) + '</pre>';
            });
        }
        function createTables() {
            fetch('/create/tables', {method: 'POST'})
            .then(response => response.json())
            .then(data => {
                document.getElementById('result').innerHTML = 
                    '<h3>Create Result:</h3><pre>' + JSON.stringify(data, null, 2) + '</pre>';
            });
        }
        </script>
    </body>
    </html>
    '''

@app.route('/delete/tables', methods=['POST'])
def delete_tables():
    try:
        tables_to_delete = ['ChatHistory', 'SlotBookings', 'Messages']
        deleted = []
        errors = []
        
        for table_name in tables_to_delete:
            try:
                table = dynamodb.Table(table_name)
                table.delete()
                deleted.append(table_name)
            except Exception as e:
                errors.append(f"{table_name}: {str(e)}")
        
        return jsonify({
            'success': True,
            'deleted_tables': deleted,
            'errors': errors,
            'message': 'Old tables deletion initiated. Wait a few minutes before creating new ones.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create/tables', methods=['POST'])
def create_tables():
    try:
        dynamodb.create_table(
            TableName='SlotBookings',
            KeySchema=[
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        dynamodb.create_table(
            TableName='ChatHistory',
            KeySchema=[
                {'AttributeName': 'conversationId', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'conversationId', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        dynamodb.create_table(
            TableName='ConversationLog',
            KeySchema=[
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        return jsonify({
            'success': True,
            'message': 'All tables created successfully. Wait a few minutes for them to become active.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/verify/aws', methods=['GET'])
def verify_aws():
    try:
        sts = boto3.client('sts', region_name=YOUR_REGION)
        identity = sts.get_caller_identity()
        return jsonify({
            'success': True,
            'account': identity.get('Account'),
            'user_id': identity.get('UserId'),
            'arn': identity.get('Arn')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)