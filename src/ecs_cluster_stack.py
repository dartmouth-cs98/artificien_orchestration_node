import string
import random
from aws_cdk import (
    core as cdk,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_rds as rds,
)


class EcsClusterStack(cdk.Stack):
    """
    Creates an ECS cluster. This ECS cluster will be the 'home' of all pygrid node deployments.
    By having only one ECS cluster and associated VPC deployment where all ECS service deployments 'live', we avoid
    spinning up unnecessary VPCs and ECS clusters, and save on cost.

    Also creates a serverless SQL DB for pygrid nodes to communicate with.
    """

    def __init__(self, scope: cdk.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.vpc = ec2.Vpc(self, "PygridVPC", max_azs=2)
        self.cluster = ecs.Cluster(self, 'PyGridCluster', vpc=self.vpc)

        # Create the DB password
        # plaintext_pw = create_password()
        plaintext_pw = 'abadpassword'
        password = cdk.SecretValue.plain_text(
            plaintext_pw
        )

        # Create an AWS Aurora Database
        username = 'pygridUser'
        default_db_name = 'pygridDB'
        postgres_port = 5432

        # Security group which allows for Postgres Ingress
        postgres_sg = ec2.SecurityGroup(self, 'PostgresSg',
                                        vpc=self.vpc, allow_all_outbound=True,
                                        security_group_name='PostgrestSg')

        postgres_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(postgres_port))

        # Database cluster itself
        self.db = rds.ServerlessCluster(
            self,
            'PyGridSQLCluster',
            engine=rds.DatabaseClusterEngine.AURORA_POSTGRESQL,
            parameter_group=rds.ParameterGroup.from_parameter_group_name(
                self, 'ParameterGroup', 'default.aurora-postgresql10'
            ),
            vpc=self.vpc,
            scaling=rds.ServerlessScalingOptions(
                auto_pause=cdk.Duration.minutes(10),
                min_capacity=rds.AuroraCapacityUnit.ACU_2,
                max_capacity=rds.AuroraCapacityUnit.ACU_8,  # we can increase the upper bound, if we require more I/O
            ),
            default_database_name=default_db_name,
            credentials=rds.Credentials.from_password(
                username=username,
                password=password
            ),
            security_groups=[postgres_sg]
        )

        # Get the Access URL for the database
        self.db_url = 'postgresql://' + username + ':' + plaintext_pw + '@' + self.db.cluster_endpoint.hostname + \
                      ':' + str(postgres_port) + '/'


def create_password():
    """
    Constructs a plaintext password. Does not store this password anywhere in the code, and does not retain it
    after deployment.
    """
    password_characters = set(string.ascii_letters + string.digits + string.punctuation)
    password_characters -= {'/', '@', '\"'}
    password_characters = ''.join(password_characters)
    password = []
    for x in range(20):
        password.append(random.choice(password_characters))

    return ''.join(password)
