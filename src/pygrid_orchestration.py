import os
import boto3
import requests
import torch as th
from decimal import Decimal
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
    features = request.json.get('features')
    labels = request.json.get('labels')

    model_id = model_id.lower()

    try:
        model_response = model_table.query(KeyConditionExpression=Key('model_id').eq(model_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 500

    if model_response['Items'] is None:
        return jsonify({'error': 'model id not found'}), 400

    try:
        dataset_response = dataset_table.query(KeyConditionExpression=Key('dataset_id').eq(dataset_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 500

    if dataset_response['Items'] is None:
        return jsonify({'error': 'dataset_id not found'}), 400

    # first validate the user has access to data requested
    owner = model_response['Items'][0]['owner_name']
    if validate_user(dataset_id, owner) is False:
        return jsonify({'error': 'user has not purchased requested dataset'}), 600

    # next, record model features and labels in the database
    model_response['Items'][0]['features'] = features
    model_response['Items'][0]['labels'] = labels
    model_table.put_item(Item=model_response['Items'][0])
    
    # if dataset hasNode, check if node is fully deployed
    if dataset_response['Items'][0]['hasNode'] is True:
        output_dict = get_outputs(stack_name=dataset_id)

        # If we are on a 'LOCALTEST', then the pygrid node won't get picked up by cloudformation
        # (since pygrid is simply running on local)
        if os.getenv('LOCALTEST') == 'True':
            nodeURL = dataset_response['Items'][0]['nodeURL']
        else:
            if output_dict is None:
                return jsonify({'status': 'node is deploying, please wait'})
            nodeURL = output_dict['PyGridNodeLoadBalancerDNS']

        # put nodeAddress into DB
        model_response['Items'][0]['node_URL'] = nodeURL
        model_table.put_item(Item=model_response['Items'][0])

        dataset_response['Items'][0]['nodeURL'] = nodeURL
        dataset_table.put_item(Item=dataset_response['Items'][0])
        print(nodeURL)
        return jsonify({'status': 'ready', 'nodeURL': nodeURL})

    # if dataset doesn't have node, deploy resources
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

@app.route("/model_loss", methods=["POST"])
def model_loss():
    """
    Receives reports of model loss and updates the DB accordingly.
    Model loss is updated on a cycle-by-cycle basis. So... each time a cycle
    completes, the loss is reset.
    """
    acc = float(request.json.get('acc'))
    loss = float(request.json.get('loss'))
    model_id = request.json.get('model_id')
    model_table = dynamodb.Table('model_table')

    # Debugging
    print('Model', model_id, 'had a loss of', loss)

    # Update the DynamoDB entry for the model
    try:
        model_response = model_table.query(KeyConditionExpression=Key('model_id').eq(model_id))
        model = model_response['Items'][0]
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 500

    # Determine the new average model loss across the cycle
    loss_sum = float(model['devices_trained_this_cycle'] * model['loss_this_cycle'])
    acc_sum = float(model['devices_trained_this_cycle'] * model['acc_this_cycle'])
    new_loss = (loss_sum + loss) / float(model['devices_trained_this_cycle'] + 1)
    new_acc = (acc_sum + acc) / float(model['devices_trained_this_cycle'] + 1)

    # Update the model loss
    model['devices_trained_this_cycle'] += 1
    model['loss_this_cycle'] = Decimal(new_loss)
    model['acc_this_cycle'] = Decimal(new_acc)
    model_table.put_item(Item=model)

    return jsonify({'status': 'model loss/acc was updated successfully'})


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
        model_response = model_table.query(KeyConditionExpression=Key('model_id').eq(model_id))
        model = model_response['Items'][0]
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 500

    # Set the new completion percentage
    model['percent_complete'] = Decimal(percent_complete)

    # Now that the cycle is complete, reset num_devices trained
    model['devices_trained_this_cycle'] = 0

    model_table.put_item(Item=model)

    # If the model is done training, retrieve it so that the user can download it
    if percent_complete == 100:
        # Do model retrieval
        try:
            retrieve(user=model['owner_name'], model_id=model_id, version=model['version'], node_url=model['node_URL'])
        except:
            return jsonify({'error': 'failed to perform model retrieval'}), 500

        # If all models left in the node are done, spin it down

    return jsonify({'status': 'model progress was updated successfully'})


@app.route("/info", methods=["POST"])
def get_info():
    # validate api key
    api_key = request.headers.get('api_key')
    dataset_id = request.json.get('dataset_id')
    resp = validate_api_key(api_key, dataset_id)
    if resp is not True:
        return jsonify({'error': 'cannot authenticate, verify provided api_key'}), 400

    dataset_table = dynamodb.Table('dataset_table')
    model_table = dynamodb.Table('model_table')

    try:
        dataset_response = dataset_table.query(KeyConditionExpression=Key('dataset_id').eq(dataset_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 400

    if not dataset_response['Items'][0]['properlySetUp']:
        dataset_response['Items'][0]['properlySetUp'] = True
        dataset_table.put_item(Item=dataset_response['Items'][0])
        return jsonify({'success': dataset_id+' is properly configured'})

    if not dataset_response['Items'][0]['hasNode']:
        return jsonify({'error': 'no node available'}), 400

    node_url = dataset_response['Items'][0]['nodeURL']

    try:
        model_response = model_table.scan(FilterExpression=Key('dataset').eq(dataset_id), ProjectionExpression='model_id, version, features, labels, percent_complete')
    except:
        return jsonify({'error': 'failed to query dynamodb'}), 400

    models = model_response['Items']
    rmodels = []

    for model in models:
        try:
            if model['percent_complete'] != 100:
                rmodels.append((model['model_id'], model['version'], model['features'], model['labels']))
        except:
            rmodels.append((model['model_id'], model['version'], model['features'], model['labels']))

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

    if user_response['Items'] is None:
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
        return jsonify({'datasets': list(resp)})


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


def validate_user(dataset_id, user_id):
    datasets = get_datasets(user_id)
    if dataset_id in datasets:
        return True
    return False


def validate_api_key(api_key, dataset_id):
    dataset_table = dynamodb.Table('dataset_table')
    user_table = dynamodb.Table('user_table')
    api_key_db = 0
    try:
        dataset_response = dataset_table.query(KeyConditionExpression=Key('dataset_id').eq(dataset_id))
    except:
        return jsonify({'error': 'failed to query dynamodb'})

    try:
        owner_username = dataset_response['Items'][0]['owner_username']
    except:
        return jsonify({'error': 'owner not listed for provided dataset_id'})

    try:
        user_response = user_table.query(
            IndexName='users_username_index',
            KeyConditionExpression=Key('username').eq(owner_username)
        )
    except:
        return jsonify({'error': 'failed to query dynamodb'})

    try:
        api_key_db = user_response['Items'][0]['api_key']
    except:
        return jsonify({'error': 'no api_key generated for user'})

    if api_key_db == api_key:
        return True
    else:
        return False


@app.after_request
def apply_caching(response):
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response


def retrieve(user, model_id, version, node_url):

    # 1. get pygrid model
    payload = {
        "name": model_id,
        "version": version,
        "checkpoint": "latest"
    }

    url = 'http://' + node_url + ":5000/model-centric/retrieve-model"
    r = requests.get(url, params=payload)
    
    # perceptron-1.2.pkl
    file_name = model_id + '-' + version + '.pkl'  # name of file
    file_loc = '/tmp/' + file_name  # local save location
    s3_loc = user + '/' + file_name  # location where file will be saved on S3 (under a user's directory)
    th.save(r.content, file_loc)

    # 2. Put model in s3 bucket
    s3 = boto3.client('s3')
    s3_bucket_name = "artificien-retrieved-models-storage"
    s3.upload_file(file_loc, s3_bucket_name, s3_loc, ExtraArgs={'ACL': 'public-read'})  # Public download
    print('Done uploading trained model to S3!')

    # https://artificien-retrieved-models-storage.s3.amazonaws.com/technigala/perceptron1.2.pkl
    bucket_url = 'https://' + s3_bucket_name + '.s3.amazonaws.com/' + s3_loc
    
    # 3. flip is_active boolean on model in dynamo
    model_table = dynamodb.Table('model_table')

    # 4. Add bucket URL to model in Dynamo
    update_response = model_table.update_item(
        Key={'model_id': model_id},
        UpdateExpression="set download_link = :r",
        ExpressionAttributeValues={
            ':r': bucket_url,
        },
    )

    if update_response:
        print("UPDATE success")