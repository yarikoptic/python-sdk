"""
Internal utilities for schema generation we don't want exposed to users.
"""

import inspect
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Mapping,
    Optional,
    Tuple,
    Type,
    get_origin,
)

from pydantic import PydanticUserError, TypeAdapter
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue
from pydantic_core import CoreSchema, core_schema
from typing_extensions import TypeAliasType

from .constants import BASE_ATTR, BASE_STATUS_ATTR, REQUEST_CONTENT, RESPONSE_CONTENT
from .function_metadata import FunctionMetadata
from .logger import logger
from .utils import die

ASYNCAPI_VERSION = '2.6.0'

# TypeAdapter works on a variety of types, try to document them here
SCHEMA_HELP_MSG = """
Valid types include any class extending from pydantic.BaseModel, dataclasses, primitives, List, Set, FrozenSet, Iterable, Dict, Mapping, Tuple, NamedTuple, TypedDict, Optional, and Union.
A complete list of valid types can be found at the following links:
For a general overview, https://docs.pydantic.dev/latest/concepts/types/
For standard library types, https://docs.pydantic.dev/latest/api/standard_library_types/
For Pydantic specific type, https://docs.pydantic.dev/latest/api/types/
For networking types, https://docs.pydantic.dev/latest/api/networks/
For a complete reference, https://docs.pydantic.dev/latest/concepts/conversion_table
"""


class GenerateTypedJsonSchema(GenerateJsonSchema):
    """
    This extends Pydantic's default JSON schema generation class.

    With any type which returns an empty dictionary or missing types, we want to invalidate these schemas.
    We can't construct a meaningful schema from these types.
    """

    def any_schema(self, schema: core_schema.AnySchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches any value.

        OVERRIDE: We get no type hints from this schema, so we need to invalidate this.
        The two big annotations to watch out for are 'object' and "typing.Any".
        This will handle 'object' in _most_ other types (i.e. List[object]), but NOT i.e. List[Any].

        It will not handle Tuples or classes in all cases; it will catch invalid types, but not missing types.

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        return self.handle_invalid_for_json_schema(
            schema, 'Any or object : dynamic typing is not allowed for INTERSECT schemas'
        )

    def is_subclass_schema(self, schema: core_schema.IsSubclassSchema) -> JsonSchemaValue:
        """Generates a JSON schema that checks if a value is a subclass of a class, equivalent to Python's `issubclass`
        method.

        OVERRIDE: Pydantic v2 returned an empty dictionary to maintain backwards compat. with v1, but we don't need this.

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        return self.handle_invalid_for_json_schema(
            schema, f'core_schema.IsSubclassSchema ({schema["cls"]})'
        )

    def list_schema(self, schema: core_schema.ListSchema) -> JsonSchemaValue:
        """Returns a schema that matches a list schema.

        OVERRIDES: we need to make sure we have an items schema, defer to Pydantic's implementation otherwise

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        if not schema.get('items_schema'):
            return self.handle_invalid_for_json_schema(
                schema, 'list subtyping may not be dynamic in INTERSECT'
            )
        return super().list_schema(schema)

    # TODO - Pydantic 2.6 will merge both tuple functions into one, use this implementation
    def tuple_positional_schema(self, schema: core_schema.TuplePositionalSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches a positional tuple schema e.g. `Tuple[int, str, bool]`.

        OVERRIDE: disallow Tuple[()] or tuple[()]), otherwise defer to Pydantic's handling

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        json_schema = super().tuple_positional_schema(schema)
        if not json_schema.get('items') and not json_schema.get('prefixItems'):
            return self.handle_invalid_for_json_schema(
                schema, 'tuple: () is not a permitted tuple argument for INTERSECT'
            )
        return json_schema

    # TODO - Pydantic 2.6 will merge both tuple functions into one, use the other function's implementation
    def tuple_variable_schema(self, schema: core_schema.TupleVariableSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches a variable tuple schema e.g. `Tuple[int, ...]`.

        OVERRIDE: disallow bare tuple typing, otherwise defer to Pydantic's handling

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        json_schema = super().tuple_variable_schema(schema)
        if not json_schema.get('items'):
            return self.handle_invalid_for_json_schema(schema, 'empty tuple typing for INTERSECT')
        return json_schema

    def set_schema(self, schema: core_schema.SetSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches a set schema.

        OVERRIDES: we need to make sure we have an items schema, defer to Pydantic's implementation otherwise

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        if not schema.get('items_schema'):
            return self.handle_invalid_for_json_schema(
                schema, 'set subtyping may not be dynamic in INTERSECT'
            )
        return super().set_schema(schema)

    def frozenset_schema(self, schema: core_schema.FrozenSetSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches a frozenset schema.

        OVERRIDES: we need to make sure we have an items schema, defer to Pydantic's implementation otherwise

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        if not schema.get('items_schema'):
            return self.handle_invalid_for_json_schema(
                schema, 'frozenset subtyping may not be dynamic in INTERSECT'
            )
        return super().frozenset_schema(schema)

    def generator_schema(self, schema: core_schema.GeneratorSchema) -> JsonSchemaValue:
        """Returns a JSON schema that represents the provided GeneratorSchema.

        OVERRIDES: we need to make sure we have an items schema, defer to Pydantic's implementation otherwise
        NOTE: at time of writing (pydantic v2.5.3), this never seems to execute when there's an error, but the superclass function
        suggests that it should. This function is kept in for backwards compatibility purposes.

        Args:
            schema: The schema.

        Returns:
            The generated JSON schema.
        """
        if not schema.get('items_schema'):
            return self.handle_invalid_for_json_schema(
                schema, 'generator yield subtyping (first argument) may not be dynamic in INTERSECT'
            )
        json_schema = super().generator_schema(schema)
        if not json_schema.get('items'):
            return self.handle_invalid_for_json_schema(
                schema, 'generator yield subtyping (first argument) may not be dynamic in INTERSECT'
            )
        return json_schema

    def dict_schema(self, schema: core_schema.DictSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches a dict schema.

        OVERRIDE: While we can defer to Pydantic's handling for the most part, we need to check two things:
        1) We need to make sure that "additionalProperties" has typing information (don't allow "Any" as the Value type)
        2) In JSON, mapping "keys" must always be strings, so check that the Key type is "str".

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        keys_schema = schema.get('keys_schema', None)
        if not keys_schema or keys_schema.get('type', None) != 'str':
            return self.handle_invalid_for_json_schema(
                schema, "dict or mapping key type needs to be 'str' for INTERSECT"
            )
        json_schema = super().dict_schema(schema)
        if not json_schema.get('additionalProperties') and not json_schema.get('patternProperties'):
            return self.handle_invalid_for_json_schema(
                schema, 'dict or mapping value type cannot be Any/object for INTERSECT'
            )
        return json_schema

    def typed_dict_schema(self, schema: core_schema.TypedDictSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches a schema that defines a typed dict.

        OVERRIDE: make sure TypedDict class has at least one property, otherwise defer to Pydantic's handling

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        json_schema = super().typed_dict_schema(schema)
        if not json_schema.get('properties'):
            return self.handle_invalid_for_json_schema(
                schema, 'TypedDict (empty TypedDict not allowed in INTERSECT)'
            )
        return json_schema

    def model_schema(self, schema: core_schema.ModelSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches a schema that defines a model.

        OVERRIDE: make sure BaseModel class has at least one property, otherwise defer to Pydantic's handling

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        json_schema = super().model_schema(schema)
        if not json_schema.get('properties'):
            return self.handle_invalid_for_json_schema(
                schema,
                f'pydantic.BaseModel "{schema["cls"].__name__}" (needs at least one property for INTERSECT)',
            )
        return json_schema

    def dataclass_schema(self, schema: core_schema.DataclassSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches a schema that defines a dataclass.

        OVERRIDE: make sure dataclass has at least one property, otherwise defer to Pydantic's handling

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """

        json_schema = super().dataclass_schema(schema)
        if not json_schema.get('properties'):
            return self.handle_invalid_for_json_schema(
                schema,
                f'dataclass "{schema["cls"].__name__}" (needs at least one property for INTERSECT)',
            )
        return json_schema

    def kw_arguments_schema(
        self,
        arguments: List[core_schema.ArgumentsParameter],
        var_kwargs_schema: Optional[CoreSchema],
    ) -> JsonSchemaValue:
        """Generates a JSON schema that matches a schema that defines a function's keyword arguments.

        OVERRIDE: Make sure at least one argument is present, otherwise defer to Pydantic's handling. (This is done to ensure future compatibility, but it currently doesn't appear to be used by Pydantic.)

        Args:
            arguments: The core schema.

        Returns:
            The generated JSON schema.
        """
        if not arguments:
            return self.handle_invalid_for_json_schema(
                var_kwargs_schema,
                'core_schema.ArgumentsSchema (missing keyword arguments, needed for INTERSECT)',
            )
        return super().kw_arguments_schema(arguments, var_kwargs_schema)

    def p_arguments_schema(
        self, arguments: List[core_schema.ArgumentsParameter], var_args_schema: Optional[CoreSchema]
    ) -> JsonSchemaValue:
        """Generates a JSON schema that matches a schema that defines a function's positional arguments.

        OVERRIDE: Make sure at least one argument is present, otherwise defer to Pydantic's handling. This is used for NamedTuples.

        Args:
            arguments: The core schema.

        Returns:
            The generated JSON schema.
        """
        if not arguments:
            return self.handle_invalid_for_json_schema(
                var_args_schema,
                'core_schema.ArgumentsSchema (missing arguments, needed for INTERSECT - are you using a NamedTuple class with no properties?)',
            )
        return super().p_arguments_schema(arguments, var_args_schema)


def _get_functions(capability: Type, attr: str) -> Generator[Tuple[str, Callable], None, None]:
    for name in dir(capability):
        method = getattr(capability, name)
        if callable(method) and hasattr(method, attr):
            yield name, method


def _merge_schema_definitions(
    adapter: TypeAdapter, schemas: Dict[str, Any], annotation: Type
) -> Dict[str, Any]:
    """
    This accomplishes two things after generating the schema:
    1) merges new schema definitions into the main schemas dictionary (NOTE: the schemas param is mutated)
    2) returns the value which will be represented in the channel payload
    """
    try:
        schema = adapter.json_schema(
            ref_template='#/components/schemas/{model}', schema_generator=GenerateTypedJsonSchema
        )
    except PydanticUserError as e:
        raise e

    definitions = schema.pop('$defs', None)
    if definitions:
        schemas.update(definitions)

    # when Pydantic generates schemas, it likes to put explicit classes into $defs
    # TypeAliasType annotations always get their own definitions
    if isinstance(annotation, TypeAliasType):
        schemas[annotation.__name__] = schema
        return {'$ref': f'#/components/schemas/{annotation.__name__}'}
    schema_type = schema.get('type')
    if schema_type == 'object':
        # Dict, OrderedDict, and Mapping lack a user-defined label, so just return the schema
        if inspect.isclass(get_origin(annotation)) and issubclass(get_origin(annotation), Mapping):
            return schema
        schemas[annotation.__name__] = schema
        return {'$ref': f'#/components/schemas/{annotation.__name__}'}
    if schema_type == 'array':
        # NamedTuples get their own definitions, all other array types do not
        if (
            inspect.isclass(annotation)
            and issubclass(annotation, Tuple)
            and hasattr(annotation, '_fields')
        ):
            schemas[annotation.__name__] = schema
            return {'$ref': f'#/components/schemas/{annotation.__name__}'}
        return schema
    if 'enum' in schema or 'const' in schema:
        # Enum typings get their own definitions, Literals are inlined
        if inspect.isclass(annotation) and issubclass(annotation, Enum):
            schemas[annotation.__name__] = schema
            return {'$ref': f'#/components/schemas/{annotation.__name__}'}
        return schema
    return schema


def _status_fn_schema(
    capability: Type, schemas: Dict[str, Any]
) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[TypeAdapter]]:
    status_fns = tuple(_get_functions(capability, BASE_STATUS_ATTR))
    if len(status_fns) > 1:
        die(
            f"Class '{capability.__name__}' should only have one function annotated with the @intersect_status() decorator."
        )
    if len(status_fns) == 0:
        logger.warning(
            f"Class '{capability.__name__}' has no function annotated with the @intersect_status() decorator. No status information will be provided when sending status messages."
        )
        return None, None, TypeAdapter(None)
    status_fn_name, status_fn = status_fns[0]
    status_signature = inspect.signature(status_fn)
    if len(status_signature.parameters) != 1:
        die(
            f"On capability '{capability.__name__}', capability status function '{status_fn_name}' should have no parameters other than 'self'"
        )
    if status_signature.return_annotation is inspect.Signature.empty:
        die(
            f"On capability '{capability.__name__}', capability status function '{status_fn_name}' should have a valid return annotation."
        )
    try:
        status_adapter = TypeAdapter(status_signature.return_annotation)
        return (
            status_fn_name,
            _merge_schema_definitions(status_adapter, schemas, status_signature.return_annotation),
            status_adapter,
        )
    except PydanticUserError as e:
        die(
            f"On capability '{capability.__name__}', return annotation '{status_signature.return_annotation}' on function '{status_fn_name}' is invalid.\n{e}"
        )


def get_schemas_and_functions(
    capability: Type,
) -> Tuple[
    Dict[str, Any],
    Tuple[Optional[str], Optional[Dict[str, Any]], TypeAdapter],
    Dict[str, Any],
    Dict[str, FunctionMetadata],
]:
    """
    This function does the bulk of introspection, and also validates the user's capability.

    Basic logic:

    - Capabilities should implement functions which represent entrypoints
    - Each entrypoint should be annotated with @intersect_message() (this sets a hidden attribute)
    - Entrypoint functions should either have no parameters, or they should
      describe all their parameters in one BaseModel-derived class.
      (NOTE: maybe allow for some other input formats?)
    """

    function_map = {}
    schemas = {}
    channels = {}

    for name, method in _get_functions(capability, BASE_ATTR):
        docstring = inspect.cleandoc(method.__doc__) if method.__doc__ else None
        signature = inspect.signature(method)
        method_params = tuple(signature.parameters.values())
        return_annotation = signature.return_annotation
        if len(method_params) == 0 or len(method_params) > 2:
            die(
                f"On capability '{capability.__name__}', function '{name}' should have 'self' and zero or one additional parameters"
            )

        # The schema format should be hard-coded and determined based on how Pydantic parses the schema.
        # See https://docs.pydantic.dev/latest/concepts/json_schema/ for that specification.
        channels[name] = {
            'publish': {
                'message': {
                    'schemaFormat': f'application/vnd.aai.asyncapi+json;version={ASYNCAPI_VERSION}',
                    'contentType': getattr(method, REQUEST_CONTENT),
                    'traits': {'$ref': '#/components/messageTraits/commonHeaders'},
                }
            },
            'subscribe': {
                'message': {
                    'schemaFormat': f'application/vnd.aai.asyncapi+json;version={ASYNCAPI_VERSION}',
                    'contentType': getattr(method, RESPONSE_CONTENT),
                    'traits': {'$ref': '#/components/messageTraits/commonHeaders'},
                }
            },
        }
        if docstring:
            channels[name]['publish']['description'] = docstring
            channels[name]['subscribe']['description'] = docstring

        # this block handles request params
        if len(method_params) == 2:
            parameter = method_params[1]
            annotation = parameter.annotation
            if annotation is inspect.Signature.empty:
                die(
                    f"On capability '{capability.__name__}', parameter '{parameter.name}' type annotation on function '{name}' missing. {SCHEMA_HELP_MSG}"
                )
            if annotation is None:
                function_cache_request_adapter = None
            else:
                try:
                    function_cache_request_adapter = TypeAdapter(annotation)
                    channels[name]['subscribe']['message']['payload'] = _merge_schema_definitions(
                        function_cache_request_adapter, schemas, annotation
                    )
                except PydanticUserError as e:
                    die(
                        f"On capability '{capability.__name__}', parameter '{parameter.name}' type annotation '{annotation}' on function '{name}' is invalid\n{e}"
                    )

        else:
            function_cache_request_adapter = None

        # this block handles response parameters
        if return_annotation is inspect.Signature.empty:
            die(
                f"On capability '{capability.__name__}', return type annotation on function '{name}' missing. {SCHEMA_HELP_MSG}"
            )
        if return_annotation is None:
            function_cache_response_adapter = None
        else:
            try:
                function_cache_response_adapter = TypeAdapter(return_annotation)
                channels[name]['publish']['message']['payload'] = _merge_schema_definitions(
                    function_cache_response_adapter, schemas, return_annotation
                )
            except PydanticUserError as e:
                die(
                    f"On capability '{capability.__name__}', return annotation '{return_annotation}' on function '{name}' is invalid.\n{e}"
                )

        function_map[name] = FunctionMetadata(
            method,
            function_cache_request_adapter,
            function_cache_response_adapter,
        )

    if len(function_map) == 0:
        die(
            f"No entrypoints detected on class '{capability.__name__}'. Please annotate at least one entrypoint with '@intersect_message()' ."
        )

    return schemas, _status_fn_schema(capability, schemas), channels, function_map