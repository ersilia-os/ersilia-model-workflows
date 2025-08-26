import os
import json
import collections
import argparse
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

parser = argparse.ArgumentParser(description="Process a file and a date string.")
parser.add_argument("--metadata_file", type=str, help="Path to the metadta file")
parser.add_argument("--field", type=str, help="Field of interest")
parser.add_argument("--content", type=str, help="Content to be incorporated")

args = parser.parse_args()

file_name = args.metadata_file
field = args.field
content = str(args.content)

if "." in content:
    if os.path.exists(content):
        with open(content, "r") as f:
            content = f.read().rstrip()
            if "," in content:
                content = content.split(',')

def _serialize(x):
    x = str(x)
    x = x.replace("'", "")
    x = x.replace('"', '')
    try:
        num = float(x)
        if "." not in x:
            return int(num)
        else:
            return num
    except:
        return x
    
def _serialize_to_list_if_necessary(x):
    if type(x) is list or type(x) is tuple:
        return list(x)
    x = str(x)
    x = x.replace("'", "")
    x = x.replace('"', '')
    x = str(x).rstrip("\n")
    if x.startswith("[") and x.endswith("]"):
        pass
    elif x.startswith("(") and x.endswith(")"):
        pass
    else:
        return x
    x = [x_.strip(" ") for x_ in x[1:-1].split(",")]
    return x

def serialize(x):
    x = _serialize_to_list_if_necessary(x)
    if type(x) is list:
        return [_serialize(x_) for x_ in x]
    else:
        return _serialize(x)

content = serialize(content)

new_order = [
    'Identifier',
    'Slug',
    'Status',
    'Title',
    'Description',
    'Deployment',
    'Source',
    'Source Type',
    'Task',
    'Subtask',
    'Input',
    'Input Dimension',
    'Output',
    'Output Dimension',
    'Output Consistency',
    'Interpretation',
    'Tag',
    'Biomedical Area',
    'Target Organism',
    'GitHub',
    'Publication Type',
    'Publication Year',
    'Publication',
    'Source Code',
    'License',
    'Contributor',
    'Contributor Profile',
    'Incorporation Date',
    'Incorporation Quarter',
    'Incorporation Year',
    'Last Packaging Date',
    'Release',
    'S3',
    'DockerHub',
    'Docker Architecture',
    'Model Size',
    'Environment Size',
    'Image Size',
    'Computational Performance 1',
    'Computational Performance 2',
    'Computational Performance 3',
    'Computational Performance 4',
    'Computational Performance 5',
]

if field not in new_order:
    raise Exception("The field" + field + "is not part of the accepted metadata fields")

def sort_dictionary_json(data):
    data_ = collections.OrderedDict()
    for k in new_order:
        if k in data:
            data_[k] = serialize(data[k])
    for k,v in data.items():
        if k not in new_order:
            data_[k] = serialize(v)
    return data_

def sort_dictionary_yml(data):
    data_ = CommentedMap()
    for k in new_order:
        if k in data:
            data_[k] = serialize(data.pop(k))
    for k,v in data.items():
        if k not in new_order:
            data_[k] = serialize(v)
    return data_

if file_name.endswith(".json"):
    with open(file_name, 'r') as f:
        data = json.load(f)
    data[field] = content
    data = sort_dictionary_json(data)       
    with open(file_name, 'w') as f:
        json.dump(data, f, indent=4)
elif file_name.endswith(".yaml") or file_name.endswith(".yml"):
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    with open(file_name, 'r') as f:
        data = yaml.load(f)
    data[field] = content
    data = sort_dictionary_yml(data)
    with open(file_name, 'w') as f:
        yaml.dump(data, f)
else:
    raise ValueError("Unsupported file format. Please provide a .json or .yaml file.")
