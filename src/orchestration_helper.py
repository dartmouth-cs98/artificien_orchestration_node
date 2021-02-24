import os
import boto3
from aws_cdk import core
from .pygrid_node_stack import PygridNodeStack
from .ecs_cluster_stack import EcsClusterStack

client = boto3.client('cloudformation')
env = core.Environment(account="719471536408", region="us-east-1")


class AppFactory:
    location = os.path.dirname(os.path.abspath(__file__))

    def __init__(self):
        self.app = core.App(outdir=self.location + '/output/')
        self.generated = {}
        return

    def make_standard_stack(self, stack_name):

        ecs_cluster_stack = EcsClusterStack(self.app, 'ecsCluster', env=env)

        # New PyGrid stack
        PygridNodeStack(
            self.app,
            stack_name,
            vpc=ecs_cluster_stack.vpc,
            cluster=ecs_cluster_stack.cluster,
            db_url=ecs_cluster_stack.db_url,
            master_node_url=os.environ.get("MASTER_NODE_URL"),
            env=env
        )

    def generate_stack(self):
        self.generated = self.app.synth()

    def launch_stack(self):
        for stack in self.generated.stacks:
            if stack.name != 'ecsCluster':
                params = {
                    'StackName': stack.name,
                    'TemplateBody': str(stack.template),
                    'Parameters': [],
                    'Capabilities': ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND'],
                }
                client.create_stack(**params)

    def delete_stack(self):
        for stack in self.generated.stacks:
            client.delete_stack(StackName=stack.name)
            # print(response)


if __name__ == "__main__":
    app_factory = AppFactory()
    app_factory.make_standard_stack("pygrid-cdk")
    app_factory.generate_stack()
    app_factory.launch_stack()
