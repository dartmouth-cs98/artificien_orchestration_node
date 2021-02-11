#!/usr/bin/env python3
# This script runs all post-deployment actions - actions which are not directly orchestrated by AWS or the CDK
import boto3
from botocore.exceptions import ClientError


def get_outputs(stack_name: str):
    """ Helper function to get CfnOutputs from deployed stacks"""
    try:
        outputs = boto3.Session().client("cloudformation").describe_stacks(
            StackName=stack_name)["Stacks"][0]["Outputs"]

        output_dict = {}
        for output in outputs:
            key = output['OutputKey']
            value = output['OutputValue']
            output_dict[key] = value

        return output_dict

    except ClientError:
        print('Cloudformation Stack might not be deployed yet')
        return None

    except KeyError:
        print('Cloudformation Outputs for the', stack_name, 'stack are not properly configured')
        return None
