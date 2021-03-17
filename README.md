# artificien_orchestration_node

## Code Details

This repo contains the core pieces of artificien's product - the so called "orchestration node", a micro-service that spins up and down pygrid nodes (a cloud service that runs federated learning for each app) on demand and routes calls from the artificien library and artificien cocoapod. On the data scientist side, it spins up a node for an app if it doesn't exist and sends models to it. On the app developer side, it sends info about models available for training to all the client devices. It also handles collating model progress and model accuracy from the pygrid node. In summary it's a flask based Rest API secured by AWS Cognito on the data scientist side and api keys on the app developer size. It is the brain of the artificien product. There are multiple parts to this repo

The core pieces are in the `src` folder.
`cfn-helper.py` is a helper function that allows us to programatically check using AWS CDK if cloud resources have been deployed yet (specifically pygrid nodes)
`ecs-cluster-stack.py` is an AWSCDK class for a Elastic Container Service (ecs) cluster shared by deployed pygrid node and a shared database. This avoids unneccesary VPCS/ECS clusters if pygrid nodes were just naively deployed so it saves on cloud services costs. This is essentially an object of the ecs cluster stack and its attributes that can be used to deploy new ecs cluster. 

`orchestration-helper.py` is a series of helper functions that allow us to spin up and down pygrid nodes on demand programatically within an `ecs-cluster-stack`. This is a very unusual thing to do - programmatically spin up cloud resources as a service - so this is actually a very complicated and difficult task in the aws cdk.
`pygrid_node_stack.py` is an AWS CDK class for the pygrid node. This is essentially an object of the pygrid stack and its attributes that can be used to deploy new pygrid nodes. 
`pygrid_orchestration.py` is 


## Execution

This is a service built ontop of the Artificien AWS CDK stack, and really isn't meant to be run outside of Artificien machines with proper AWS credentials. However is someone was inclined, they could run the mas

## Example

By the time you reach the last few cells in the tutorial, your notebook should look like [this](tutorial_sc_example.png)

## Authors

- Matthew Kenney '21
- Jake Epstein '21

## Acknowledgements

Special thanks to Professor Tim Tregubov for his guidance during our two-term COSC 098 course.
