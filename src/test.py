import boto3
from boto3.dynamodb.conditions import Key
region_name = "us-east-1"

try:
    ecs_client = boto3.client('ecs')

except BaseException as exe:
    print(exe)

dynamodb = boto3.resource('dynamodb', region_name=region_name)

if __name__ == '__main__':
    dataset_id = 'dataSetFive'
    dataset_table = dynamodb.Table('dataset_table')
    model_table = dynamodb.Table('model_table')

    try:
        dataset_response = dataset_table.query(KeyConditionExpression=Key('dataset_id').eq(dataset_id))
    except:
        print('error failed to query dynamodb')
    if not dataset_response['Items'][0]['hasNode']:
        print('error no node available')

    node_url = dataset_response['Items'][0]['nodeURL']
    print(node_url)
    try:
        model_response = model_table.scan(FilterExpression=Key('dataset').eq(dataset_id), ProjectionExpression='model_id')
    except:
        print('error: failed to query dynamodb')
    models = model_response['Items']
    rmodels = []
    for model in models:
        rmodels.append(model['model_id'])
    print(rmodels)