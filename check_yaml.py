#!/usr/bin/env python3
import yaml
import sys
from collections import defaultdict

def check_yaml_structure(filename):
    try:
        with open(filename, 'r') as f:
            content = f.read()
        
        # Try to parse with a custom loader that handles CloudFormation intrinsics
        class CloudFormationLoader(yaml.SafeLoader):
            pass
        
        def construct_ref(loader, node):
            return {'Ref': loader.construct_scalar(node)}
        
        def construct_getatt(loader, node):
            if isinstance(node, yaml.ScalarNode):
                return {'Fn::GetAtt': loader.construct_scalar(node)}
            elif isinstance(node, yaml.SequenceNode):
                return {'Fn::GetAtt': loader.construct_sequence(node)}
        
        def construct_sub(loader, node):
            if isinstance(node, yaml.ScalarNode):
                return {'Fn::Sub': loader.construct_scalar(node)}
            elif isinstance(node, yaml.SequenceNode):
                return {'Fn::Sub': loader.construct_sequence(node)}
            else:
                raise yaml.constructor.ConstructorError(None, None,
                    "expected a scalar or sequence node, but found %s" % node.id,
                    node.start_mark)
        
        def construct_join(loader, node):
            return {'Fn::Join': loader.construct_sequence(node)}
        
        def construct_importvalue(loader, node):
            return {'Fn::ImportValue': loader.construct_scalar(node)}
        
        CloudFormationLoader.add_constructor('!Ref', construct_ref)
        CloudFormationLoader.add_constructor('!GetAtt', construct_getatt)
        CloudFormationLoader.add_constructor('!Sub', construct_sub)
        CloudFormationLoader.add_constructor('!Join', construct_join)
        CloudFormationLoader.add_constructor('!ImportValue', construct_importvalue)
        
        # Parse the YAML
        data = yaml.load(content, Loader=CloudFormationLoader)
        print("YAML parsed successfully!")
        
        # Check for duplicate keys in outputs
        if 'Outputs' in data:
            outputs = data['Outputs']
            print(f"Found {len(outputs)} outputs")
            
            # Look for any unhashable types
            def check_unhashable(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if isinstance(key, (dict, list)):
                            print(f"Found unhashable key at {path}.{key}: {type(key)}")
                        check_unhashable(value, f"{path}.{key}")
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        check_unhashable(item, f"{path}[{i}]")
            
            check_unhashable(data)
        
        return True
        
    except Exception as e:
        print(f"Error parsing YAML: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = check_yaml_structure('template-app-ecs-tasks.yml')
    sys.exit(0 if success else 1)
