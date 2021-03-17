# artificien_orchestration_node

## Code Details

This repo contains the core pieces of artificien's product - the so called "orchestration node", a micro-service that spins up and down pygrid nodes (a cloud service that runs federated learning for each app) on demand and routes calls from the artificien library and artificien cocoapod. On the data scientist side, it spins up a node for an app if it doesn't exist and sends models to it. On the app developer side, it sends info about models available for training to all the client devices. It also handles collating model progress and model accuracy from the pygrid node. In summary it's a flask based Rest API secured by AWS Cognito on the data scientist side and api keys on the app developer size. It is the brain of the artificien product. There are multiple parts to this repo

The core pieces are in the `src` folder. <br />
`cfn-helper.py` is a helper function that allows us to programatically check using AWS CDK if cloud resources have been deployed yet (specifically pygrid nodes) <br />
`ecs-cluster-stack.py` is an AWSCDK class for a Elastic Container Service (ecs) cluster shared by deployed pygrid node and a shared database. This avoids unneccesary VPCS/ECS clusters if pygrid nodes were just naively deployed so it saves on cloud services costs. This is essentially an object of the ecs cluster stack and its attributes that can be used to deploy new ecs cluster. <br />
`orchestration-helper.py` is a series of helper functions that allow us to spin up and down pygrid nodes on demand programatically within an `ecs-cluster-stack`. This is a very unusual thing to do - programmatically spin up cloud resources as a service - so this is actually a very complicated and difficult task in the aws cdk. <br />
`pygrid_node_stack.py` is an AWS CDK class for the pygrid node. This is essentially an object of the pygrid stack and its attributes that can be used to deploy new pygrid nodes. <br />
`pygrid_orchestration.py` is the master node service. It's a flask based rest service that uses all of the above objects and helper functions to orchestrate artificien's federated learning marketplace.

Upon fresh commit, a github action checks if there were any changes to the stack. If there were, it compiles and updates the dockerfile in the main repo automatically and loads the new pygrid orchestration node to the cloud.


## Execution

This is a service built ontop of the Artificien AWS CDK stack, and really isn't meant to be run outside of Artificien machines with proper AWS credentials. However if someone was inclined, they could run the the pygrid orchestration node locally by adding a main method at the bottom with `app.run(...)` (just the normal flask run command) and calling `python pygrid_orchestration.py`. As they'll lack the credentials to spin up cloud resources and permissions to make most of the calls, there's not much they could do here. This isn't meant to be used by anybody - it's supposed to be a backend secure service only usable by artificien.

## Deployment
This service is deployed via our [artificien infrastructure](https://github.com/dartmouth-cs98/artificien_infrastructure) repository as an Elastic Container Service. Whenever this repo is updated, we've configured a Github Action to build the code, create a Docker Image which can run the code, and push that docker image to our [DockerHub repository](https://hub.docker.com/repository/docker/mkenney1/artificien_orchestration). The latest version of this image is then pulled by our ECS service and the service is automatically updated as we add new changes to this repo.

## Authors

- Jake Epstein '21 - who build the majority of this code base.
- Matthew Kenney '21 - who figured out how to deploy the service, and has added some endpoints and functionality after Jake's up-front work.

## Acknowledgements

Special thanks to Professor Tim Tregubov for his guidance during our two-term COSC 098 course.
