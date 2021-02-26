import boto3
import requests
import torch as th
from boto3.dynamodb.conditions import Key
from flask import Flask, jsonify, request
from .orchestration_helper import AppFactory
from .cfn_helper import get_outputs
from flask_cognito import CognitoAuth, cognito_auth_required
import secrets


app = Flask(__name__)
app.config.update({
    'COGNITO_REGION': 'us-east-1',
    'COGNITO_USERPOOL_ID': 'us-east-1_gxjsNZ82v',

    # optional
    'COGNITO_APP_CLIENT_ID': '5nrhkbejfsq8mgi5jc08586maa',  # client ID you wish to verify user is authenticated against
    'COGNITO_CHECK_TOKEN_EXPIRATION': False,  # disable token expiration checking for testing purposes
    'COGNITO_JWT_HEADER_NAME': 'Authorization',
    'COGNITO_JWT_HEADER_PREFIX': 'Bearer',
})
region_name = "us-east-1"
length = 16
cogauth = CognitoAuth(app)

try:
    ecs_client = boto3.client('ecs')

except BaseException as exe:
    print(exe)

dynamodb = boto3.resource('dynamodb', region_name=region_name)


# check api status, ping to test
@app.route("/")
def status():
    return "Running"


# spin up a new node for an app developer
@app.route("/create", methods=["POST"])
@cognito_auth_required
def create_node():
    # grab model id, query model_table to check if a node has already been spun up for model
    model_table = dynamodb.Table('model_table')
    dataset_table = dynamodb.Table('dataset_table')
    model_id = request.json.get('model_id')
    dataset_id = request.json.get('dataset_id')
    model_id = model_id.lower()
    print(model_id)
    print(dataset_id)
    try:
        model_response = model_table.query(KeyConditionExpression=Key('model_id').eq(model_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 500
    print(model_response)

    if model_response['Items'] is None:
        return jsonify({'error': 'model id not found'}), 400

    try:
        dataset_response = dataset_table.query(KeyConditionExpression=Key('dataset_id').eq(dataset_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 500
    print(dataset_response)

    if dataset_response['Items'] is None:
        return jsonify({'error': 'dataset_id not found'}), 400

    # if model hasNode, check if node is fully deployed
    if dataset_response['Items'][0]['hasNode'] is True:
        output_dict = get_outputs(stack_name=dataset_id)
        if output_dict is None:
            return jsonify({'status': 'node is deploying, please wait'})
        nodeURL = output_dict['PyGridNodeLoadBalancerDNS']

        # put nodeAddress into DBd
        model_response['Items'][0]['node_URL'] = nodeURL
        model_table.put_item(Item=model_response['Items'][0])

        dataset_response['Items'][0]['nodeURL'] = nodeURL
        dataset_table.put_item(Item=dataset_response['Items'][0])
        print(nodeURL)
        return jsonify({'status': 'ready', 'nodeURL': nodeURL})

    # if node hasn't been loaded yet, first validate the user has access to data
    owner = model_response['Items'][0]['owner_name']
    if validate_user(model_id, owner) is False:
         return jsonify({'error': 'user has not purchased requested dataset'}), 600

    # deploy resources
    app_factory = AppFactory()
    app_factory.make_standard_stack(dataset_id)
    app_factory.generate_stack()
    app_factory.launch_stack()
    print("Deploying")

    # set hasNode to true
    dataset_response['Items'][0]['hasNode'] = True
    dataset_table.put_item(Item=dataset_response['Items'][0])
    return jsonify({'status': 'node is starting to deploy. This may take a few minutes'})


# delete node of an app developer
@app.route("/delete", methods=["POST"])
@cognito_auth_required
def delete_node():
    return None


@app.route("/model_progress", methods=["POST"])
def model_progress():
    """ Updates the percent complete attribute of a model, and retrieves the model if it is done training """

    # Get the new model complete metric from PyGrid
    model_id = request.json.get('model_id')
    percent_complete = request.json.get('percent_complete')
    model_table = dynamodb.Table('model_table')

    # Debugging
    print('Got model', model_id, 'from PyGrid, which is', percent_complete, 'percent complete')

    # Update the DynamoDB entry for 'percent_complete'
    try:
        model = model_table.query(KeyConditionExpression=Key('model_id').eq(model_id))['Items'][0]
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 500

    model['percent_complete'] = percent_complete
    model_table.put_item(Item=model)

    # If the model is done training, retrieve it so that the user can download it
    if percent_complete == 100:
        # Do model retrieval
        try:
            retrieve(user=model['owner_name'], model_id=model_id, version=model['version'], node_url=model['node_URL'])
        except:
            return jsonify({'error': 'failed to perform model retrieval'}), 500

        # If all models left in the node are done, spin it down

    return jsonify({'status': 'model completion was updated successfully'})


@app.route("/info", methods=["POST"])
def get_info():
    #validate api key
    api_key = request.headers.get('api_key')
    dataset_id = request.json.get('dataset_id')

    if not validate_api_key(api_key, dataset_id):
        return jsonify({'error': 'cannot authenticate, verify provided api_key'}), 400

    dataset_table = dynamodb.Table('dataset_table')
    model_table = dynamodb.Table('model_table')

    try:
        dataset_response = dataset_table.query(KeyConditionExpression=Key('dataset_id').eq(dataset_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 400
    if not dataset_response['Items'][0]['hasNode']:
        return jsonify({'error':'no node available'}), 400

    node_url = dataset_response['Items'][0]['nodeURL']

    try:
        model_response = model_table.scan(FilterExpression=Key('dataset').eq(dataset_id), ProjectionExpression='model_id, version')
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 400

    models = model_response['Items']
    rmodels = []

    for model in models:
        rmodels.append((model['model_id'], model['version']))

    return jsonify({'models': rmodels, 'nodeURL': node_url})


@app.route("/generate_key", methods=["POST"])
@cognito_auth_required
def generate_key():
    user_id = request.json.get('user_id')
    api_key = secrets.token_urlsafe(length)
    user_table = dynamodb.Table('user_table')
    try:
        user_response = user_table.query(KeyConditionExpression=Key('user_id').eq(user_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 500

    if user_response['Items'][0] is None:
        return jsonify({'error': 'user not found'}), 400

    user_response['Items'][0]['api_key'] = api_key
    user_table.put_item(Item=user_response['Items'][0])

    return jsonify({'api_key': api_key})


@app.route("/get_datasets", methods=["POST"])
@cognito_auth_required
def get_my_datasets():
    user_id = request.json.get('user_id')
    resp = get_datasets(user_id)
    if resp == -1:
        return jsonify({'datasets': 'no purchased datasets available'})
    else:
        return jsonify({'datasets': resp})


def get_datasets(user_id):
    user_table = dynamodb.Table('user_table')

    response = user_table.query(
        IndexName='users_username_index',
        KeyConditionExpression=Key('username').eq(user_id)
    )

    try:
        datasets = set(response['Items'][0]['datasets_purchased'])
        return datasets
    except:
        return -1


def validate_user(model_id, user_id):
    datasets = get_datasets(user_id)
    if model_id in datasets:
        return True
    return False


def validate_api_key(api_key, dataset_id):
    dataset_table = dynamodb.Table('dataset_table')
    user_table = dynamodb.Table('user_table')
    try:
        dataset_response = dataset_table.query(KeyConditionExpression=Key('dataset_id').eq(dataset_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 400

    try:
        owner_username = dataset_response['Items'][0]['owner_username']
    except:
        return jsonify({'error': 'owner not listed for provided dataset_id'}), 400

    try:
        user_response = user_table.query(
            IndexName='users_username_index',
            KeyConditionExpression=Key('username').eq(owner_username)
        )
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 400

    try:
        api_key_db = user_response['Items'][0]['api_key']
    except:
        return jsonify({'error': 'no api_key generated for user'}), 400

    if api_key_db == api_key:
        return True
    else:
        return False


def retrieve(user, model_id, version, node_url):

    # 1. get pygrid model
    payload = {
        "name": model_id,
        "version": version,
        "checkpoint": "latest"
    }

    url = node_url + "/model-centric/retrieve-model"
    r = requests.get(url, params=payload)
    th.save(r.content, '/tmp/model.pkl')  # only the /tmp directory in lambda is writable

    # 2. Put model in s3 bucket
    s3 = boto3.client('s3')
    region = region_name
    s3_bucket_name = "artificien-retrieved-models-storage"
    file_name = user + model_id + version + '/tmp/model.pkl'
    s3.upload_file('/tmp/model.pkl', s3_bucket_name, file_name)
    print('done!')

    bucket_url = 'https://s3.console.aws.amazon.com/s3/object/' + s3_bucket_name + '?region=' + region + '&prefix=' + file_name

    # 3. flip is_active boolean on model in dynamo
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('model_table')

    # 4. Add bucket URL to model in Dynamo
    update_response = table.update_item(
        Key={'model_id': model_id},
        UpdateExpression="set download_link = :r",
        ExpressionAttributeValues={
            ':r': bucket_url,
        },
    )

    if update_response:
        print("UPDATE success")