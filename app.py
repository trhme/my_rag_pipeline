#!/usr/bin/env python3
import aws_cdk as cdk
from pipeline_stack import ServerlessRagPipelineStack

app = cdk.App()
ServerlessRagPipelineStack(app, "ServerlessRagPipelineStack")
app.synth()
