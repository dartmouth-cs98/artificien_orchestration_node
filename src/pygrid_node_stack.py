from aws_cdk import (
    core as cdk,
    aws_logs as logs,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as load_balancer,
    aws_ecs_patterns as ecs_patterns,
)


class PygridNodeStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, id: str, vpc: ec2.Vpc,
                 cluster: ecs.Cluster, db_url: str, master_node_url: str, **kwargs) -> None:

        super().__init__(scope, id, **kwargs)

        self.service = ecs_patterns.NetworkLoadBalancedFargateService(
            self, 
            'PyGridService',
            # Resource

            cluster=cluster,
            cpu=512,
            memory_limit_mib=2048,
            desired_count=1,

            # Load balancer config
            public_load_balancer=True,
            listener_port=5000,

            # Task image options
            task_image_options=ecs_patterns.NetworkLoadBalancedTaskImageOptions(
                container_name='pygrid_node',
                container_port=5000,
                image=ecs.ContainerImage.from_registry('mkenney1/artificien_pygrid:latest'),
                environment={
                    'NODE_ID': id.lower(),  # Use stack ID as node ID
                    'ADDRESS': 'http://localhost:5000',
                    'PORT': '5000',
                    'DATABASE_URL': db_url,
                    'MASTER_NODE_URL': master_node_url,
                },
                enable_logging=True,
                log_driver=ecs.AwsLogDriver(
                    stream_prefix='PyGridNode',
                    log_group=logs.LogGroup(
                        self, 'PyGridLogGroup',
                        removal_policy=cdk.RemovalPolicy.DESTROY,
                        retention=logs.RetentionDays.ONE_MONTH
                    )
                )
            ),
            load_balancer=load_balancer.NetworkLoadBalancer(
                self, 'PyGridLoadBalancer',
                vpc=vpc,
                internet_facing=True,
                cross_zone_enabled=True
            )
        )

        # Allow ingress
        all_ports = ec2.Port(
            protocol=ec2.Protocol.TCP,
            from_port=0,
            to_port=65535,
            string_representation='All'
        )
        self.service.service.connections.allow_from_any_ipv4(all_ports)
        
        # Health Check
        self.service.target_group.configure_health_check(
            port='traffic-port',
            protocol=load_balancer.Protocol.TCP
        )
        
        # Get domain name of load balancer and output it to the console
        cdk.CfnOutput(self, 'PyGridNodeLoadBalancerDNS', value=self.service.load_balancer.load_balancer_dns_name)
