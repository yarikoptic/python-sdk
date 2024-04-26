"""
This module is meant to test several invalid schemas.

ALL invalid schemas should raise a SystemExit and critically log the problem.

Note that the schema writer causes a system exit immediately on error, so try to only test
one error at a time.

General rules of "invalids":
- annotation missing entirely (though this is ok for @intersect_status())
- too many / not enough parameters for function (status must only have 'self', message can only have 'self' and possibly one additional parameter)
- missing parameter or return annotations for function
- annotation or nested annotation resolves to Any/object typing (this provides no typing information in schema, so cannot be used)
"""

import datetime
from collections import namedtuple
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Generator, List, NamedTuple, Set, Tuple, TypeVar

import pytest
from annotated_types import Gt
from intersect_sdk import (
    HierarchyConfig,
    IntersectBaseCapabilityImplementation,
    get_schema_from_capability_implementation,
    intersect_message,
    intersect_status,
)
from pydantic import BaseModel, Field
from typing_extensions import Annotated, TypeAliasType, TypedDict

# HELPERS #########################

TEST_HIERARCHY_CONFIG = HierarchyConfig(
    organization='test',
    facility='test',
    system='test',
    service='test',
)


def get_schema_helper(test_type: type):
    return get_schema_from_capability_implementation(test_type, TEST_HIERARCHY_CONFIG)


# MESSAGE TESTS ###########################


# this class has no @intersect_message annotation
class MissingIntersectMessage(IntersectBaseCapabilityImplementation):
    def do_something(self, one: int) -> int: ...


def test_disallow_missing_annotation(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MissingIntersectMessage)
    assert 'has no function annotated' in caplog.text


# more than one parameter is forbidden
class TooManyParametersOnIntersectMessage(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def too_many_params(self, one: int, two: int) -> int: ...


def test_disallow_too_many_parameters(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(TooManyParametersOnIntersectMessage)
    assert 'zero or one additional parameters' in caplog.text


# annotated methods should be normal methods (not classmethods or staticmethods)
# so this is really just catching the lack of a "self" annotation
class MissingParametersOnIntersectMessage(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def forgot_params() -> int: ...


def test_disallow_zero_parameters(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MissingParametersOnIntersectMessage)
    assert 'zero or one additional parameters' in caplog.text


# should fail because the function parameter is missing a type annotation
class MissingParameterAnnotation(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def forgot_param_annotation(self, param) -> int:  # noqa: ANN001 (the point of the test...)
        ...


def test_disallow_missing_parameter_annotation(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MissingParameterAnnotation)
    assert (
        "parameter 'param' type annotation on function 'forgot_param_annotation' missing"
        in caplog.text
    )


# should fail because the function return annotation is missing
class MissingReturnTypeAnnotation(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def forgot_return_annotation(self, param: int): ...


def test_disallow_missing_return_annotation(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MissingReturnTypeAnnotation)
    assert "return type annotation on function 'forgot_return_annotation' missing" in caplog.text


# should fail because Pydantic can't parse the inner class
class PydanticUnparsable(IntersectBaseCapabilityImplementation):
    class PydanticUnparsableInner:
        one: int
        two: bool
        three: str

    @intersect_message()
    def cant_parse_annotation(self, unparseable: PydanticUnparsableInner) -> None: ...


def test_disallow_unparsable_annotation(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(PydanticUnparsable)
    assert (
        "On capability 'PydanticUnparsable', parameter 'unparseable' type annotation" in caplog.text
    )
    assert "on function 'cant_parse_annotation' is invalid" in caplog.text


# should fail because return type is object (dynamic typing)
class MockObject(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self) -> object: ...


def test_disallow_object_typing(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockObject)
    assert 'return annotation' in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because return type has a subtyping object (dynamic typing)
# note that 'object' is evalutated exactly like it is as a root type
class MockObjectSubtype(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self) -> List[object]: ...


def test_disallow_object_subtyping(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockObjectSubtype)
    assert 'return annotation' in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because annotation type is Any (dynamic typing)
class MockAny(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: Any) -> None: ...


def test_disallow_any_typing(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAny)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because List has an Any typing
class MockAnyList(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: List[Any]) -> None: ...


def test_disallow_dynamic_list_subtyping(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAnyList)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'list subtyping may not be dynamic in INTERSECT' in caplog.text


# should fail because List's inner typing provides no information on typing
# this will fail on the "Any" schema, not the "List" schema
class MockComplexDynamicList(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: List[namedtuple('Point', ['x', 'y'])]) -> None:  # noqa: PYI024 (this is the point of testing this...)
        ...


def test_disallow_dynamic_list_subtyping_complex(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockComplexDynamicList)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because Set has an Any typing
class MockAnySet(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: Set[Any]) -> None: ...


def test_disallow_dynamic_set_subtyping(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAnySet)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'set subtyping may not be dynamic in INTERSECT' in caplog.text


# should fail because FrozenSet has an Any typing
class MockAnyFrozenSet(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: FrozenSet[Any]) -> None: ...


def test_disallow_dynamic_frozenset_subtyping(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAnyFrozenSet)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'frozenset subtyping may not be dynamic in INTERSECT' in caplog.text


# should fail because the YIELD type of "Generator" has an Any typing (the other two types do not matter)
# NOTE: for some reason, the generator
class MockAnyGenerator(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: Generator[Any, int, int]) -> None: ...


def test_disallow_dynamic_generator_subtyping(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAnyGenerator)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because Dict key type MUST be "str", "int", or "float".
# In JSON Schema, keys must be strings, and unless the schema advertises itself as such,
# we can't guarantee that we can cast the keys to any other type.
class MockNonStrDictKey(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: Dict[List[int], str]) -> None: ...


def test_disallow_non_str_dict_key_type(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockNonStrDictKey)
    assert "parameter 'param' type annotation" in caplog.text
    assert (
        "dict or mapping: key type needs to be 'str', 'int', or 'float' for INTERSECT"
        in caplog.text
    )


# should fail because Dict value has an Any typing (this should cover all other mapping types as well)
class MockAnyDictValue(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: Dict[str, Any]) -> None: ...


def test_disallow_dynamic_dict_value_type(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAnyDictValue)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'dict or mapping: value type cannot be Any/object for INTERSECT' in caplog.text


# should fail because Tuple has an Any typing
class MockAnyTuple(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: Tuple[int, str, Any, bool]) -> None: ...


def test_disallow_dynamic_tuple_subtyping(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAnyTuple)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because namedtuple factory function has no typings
class MockAnyNamedTuple(IntersectBaseCapabilityImplementation):
    InnerType = namedtuple('Point', ['x', 'y'])  # noqa: PYI024 (we're explicitly checking the untyped version...)

    @intersect_message()
    def mock_message(self, param: InnerType) -> None: ...


def test_disallow_dynamic_typing_namedtuple(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAnyNamedTuple)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# the Outer param fails because the typing of Inner.two is "Any"
class MockAnyNestedClass(IntersectBaseCapabilityImplementation):
    class Outer(BaseModel):
        @dataclass
        class Inner:
            one: int
            two: Any

        one: str
        two: Inner

    @intersect_message()
    def mock_message(self, param: Outer) -> None: ...


def test_disallow_dynamic_typing_nested(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAnyNestedClass)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because trying to use bare list without item type annotation
class MockBareList(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self) -> list: ...


def test_disallow_typeless_list(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockBareList)
    assert 'return annotation' in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because trying to use tuple with no type annotations (tuples are a special case regarding generics)
class MockBareTuple(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self) -> tuple: ...


def test_disallow_typeless_tuple(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockBareTuple)
    assert 'return annotation' in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because we're explicitly checking for this tuple type annotation
class MockAmbiguousTuple(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mock_message(self, param: Tuple[()]) -> None: ...


def test_disallow_ambiguous_tuple(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MockAmbiguousTuple)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'Tuple must have non-empty types and not use () as a type for INTERSECT' in caplog.text


# should fail because NamedTuple has no properties
class EmptyNamedTuple(IntersectBaseCapabilityImplementation):
    class Inner(NamedTuple):
        pass

    @intersect_message()
    def mock_message(self, param: Inner) -> None: ...


def test_disallow_empty_namedtuple(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(EmptyNamedTuple)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'missing arguments, needed for INTERSECT' in caplog.text


# should fail because TypedDict has no properties
class EmptyTypedDict(IntersectBaseCapabilityImplementation):
    class Inner(TypedDict):
        pass

    @intersect_message()
    def mock_message(self, param: Inner) -> None: ...


def test_disallow_empty_typeddict(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(EmptyTypedDict)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'empty TypedDict not allowed in INTERSECT' in caplog.text


# should fail because BaseModel has no properties
class EmptyBaseModel(IntersectBaseCapabilityImplementation):
    class Inner(BaseModel):
        def not_a_property(self):
            pass

    @intersect_message()
    def mock_message(self, param: Inner) -> None: ...


def test_disallow_empty_basemodel(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(EmptyBaseModel)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'needs at least one property for INTERSECT' in caplog.text


# should fail because dataclass has no properties
class EmptyDataclass(IntersectBaseCapabilityImplementation):
    @dataclass
    class Inner:
        def not_a_property(self):
            pass

    @intersect_message()
    def mock_message(self, param: Inner) -> None: ...


def test_disallow_empty_dataclass(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(EmptyDataclass)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'needs at least one property for INTERSECT' in caplog.text


# should fail because the TypeVar is ambigous and would resolve to "Any"
class AmbiguousTypeAliasType(IntersectBaseCapabilityImplementation):
    T = TypeVar('T')
    PositiveList = TypeAliasType('PositiveList', List[Annotated[T, Gt(0)]], type_params=(T,))

    @intersect_message()
    def mock_message(self, param: PositiveList) -> None: ...


def test_disallow_ambiguous_typealiastype(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(AmbiguousTypeAliasType)
    assert "parameter 'param' type annotation" in caplog.text
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# STATUS TESTS ################################################################


# should fail because only one status function is allowed
class TooManyStatusFunctions(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def not_the_problem(self, one: int) -> int: ...

    @intersect_status()
    def status_one(self, one: int) -> int: ...

    @intersect_status
    def status_two(self, one: str) -> str: ...


def test_disallow_too_many_status_functions(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(TooManyStatusFunctions)
    assert (
        'should only have one function annotated with the @intersect_status() decorator'
        in caplog.text
    )


# should fail because intersect_status function may not have ANY parameters
class TooManyParametersOnIntersectStatus(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def not_the_problem(self, one: int) -> int: ...

    @intersect_status()
    def too_many_params(self, one: int) -> int: ...


def test_disallow_too_many_parameters_status(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(TooManyParametersOnIntersectStatus)
    assert "should have no parameters other than 'self'" in caplog.text


# annotated methods should be normal methods (not classmethods or staticmethods)
# so this is really just catching the lack of a "self" annotation
class MissingSelfOnIntersectStatus(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def not_the_problem(self, one: int) -> int: ...

    @intersect_status()
    def forgot_params() -> int: ...


def test_disallow_zero_parameters_status(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MissingSelfOnIntersectStatus)
    assert "should have no parameters other than 'self'" in caplog.text


# should fail because return annotation is missing
class MissingReturnAnnotationOnStatus(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def not_the_problem(self, one: int) -> int: ...

    @intersect_status()
    def missing_return_annotation(self): ...


def test_disallow_missing_return_annotation_status(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MissingReturnAnnotationOnStatus)
    assert "'missing_return_annotation' should have a valid return annotation." in caplog.text


# should fail because return annotation is a dynamic typing
# (we're only testing one example here, for more extensive examples look at the @intersect_message() tests)
class InvalidReturnAnnotationOnStatus(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def not_the_problem(self, one: int) -> int: ...

    @intersect_status()
    def missing_return_annotation(self) -> Any: ...


def test_disallow_invalid_return_annotation_status(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(InvalidReturnAnnotationOnStatus)
    assert (
        "return annotation 'typing.Any' on function 'missing_return_annotation' is invalid."
        in caplog.text
    )
    assert 'dynamic typing is not allowed for INTERSECT schemas' in caplog.text


# should fail because INTERSECT functions can only use positional args
# (we do allow the '/' "positional only" annotation, but we also prohibit *args and **kwargs because they are misleading)
class FunctionHasKeywordOnlyParameters(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def keyword_only_params(self, *, kw: int) -> int: ...


def test_disallow_keyword_only(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(FunctionHasKeywordOnlyParameters)
    assert 'should not use keyword or variable length arguments' in caplog.text


# should fail because we explicitly disallow @classmethod annotations
class ClassMethod(IntersectBaseCapabilityImplementation):
    @classmethod
    @intersect_message()
    def bad_annotations(cls, param: bool) -> bool: ...


def test_disallow_classmethod(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(ClassMethod)
    assert 'INTERSECT annotations cannot be used with @classmethod' in caplog.text


# should fail because too many parameters for static methods (static methods use one fewer param than instance methods)
class StaticMethodTooManyParams(IntersectBaseCapabilityImplementation):
    @staticmethod
    @intersect_message()
    def too_many_params(one: bool, two: bool) -> bool: ...


def test_disallow_staticmethod_too_many_params(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(StaticMethodTooManyParams)
    assert 'zero or one additional parameters' in caplog.text


# should fail because static method parameters still need annotations
class StaticMethodMissingParamAnnotation(IntersectBaseCapabilityImplementation):
    @staticmethod
    @intersect_message()
    def missing_param_annotation(one) -> bool:  # noqa: ANN001 (the point)
        ...


def test_disallow_staticmethod_missing_param_annotation(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(StaticMethodMissingParamAnnotation)
    assert (
        "parameter 'one' type annotation on function 'missing_param_annotation' missing"
        in caplog.text
    )


# this just tests the Pythonic "default" style argument, you can use defaults with Annotated[int, Field(default=1)]
class DefaultArgumentInFunctionSignature(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def disallow_default_param(self, one: int = 4) -> int: ...


def test_disallow_default_argument_in_function_signature(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(DefaultArgumentInFunctionSignature)
    assert 'should not use a default value in the function parameter' in caplog.text


# should fail because default value mismatches annotation
class MismatchingDefaultType(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mismatching_default_type(self, one: Annotated[int, Field(default='red')]) -> bool: ...


def test_mismatching_default_type(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MismatchingDefaultType)
    assert 'does not validate against schema' in caplog.text


# should fail because nested class's default value mismatches annotation
class MismatchingDefaultTypeNested(IntersectBaseCapabilityImplementation):
    class Nested(BaseModel):
        one: int = 'red'

    @intersect_message()
    def mismatching_default_type(self, one: Nested) -> bool: ...


def test_mismatching_default_type_nested(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MismatchingDefaultTypeNested)
    assert 'does not validate against schema' in caplog.text


# should fail because nested class's default value mismatches annotation
class MismatchingDefaultTypeNested2(IntersectBaseCapabilityImplementation):
    class Nested(BaseModel):
        one: int = 'red'

    @intersect_message()
    def mismatching_default_type(self, one: Annotated[Nested, Field(default=Nested())]) -> bool: ...


def test_mismatching_default_type_nested_2(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MismatchingDefaultTypeNested2)
    assert 'does not validate against schema' in caplog.text


# should fail because lambda x: x is a default which can't be serialized
class DefaultNotSerializable(IntersectBaseCapabilityImplementation):
    class Nested(BaseModel):
        one: int = lambda x: x

    @intersect_message()
    def mismatching_default_type(self, one: Annotated[Nested, Field(default=Nested())]) -> bool: ...


def test_default_not_serializable(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(DefaultNotSerializable)
    assert 'is not JSON serializable' in caplog.text


# should fail because we cannot serialize the defaults
class InvalidNestedDefaults(IntersectBaseCapabilityImplementation):
    # note that it's import for each level of nesting to have the exact same field names in this instance, since everything is a default
    # if the two inner classes had different property names, the classes would validate successfully UNLESS you use Pydantic's ConfigDict "Extra.forbid"
    # (this translates to "additionalProperties = false" in JSON schema)
    @dataclass
    class NestedInt:
        @dataclass
        class Inner:
            field: int = 4

        field: Inner = Inner()  # noqa: RUF009 (testing bad code)

    @dataclass
    class NestedStr:
        @dataclass
        class Inner:
            field: str = 'red'

        field: Inner = Inner()  # noqa: RUF009 (testing bad code)

    @intersect_message()
    def mismatching_default_type(
        self, one: Annotated[NestedStr, Field(default=NestedInt())]
    ) -> bool: ...


def test_invalid_nested_defaults(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(InvalidNestedDefaults)
    assert "Invalid nested validation regarding defaults: 4 is not of type 'string'" in caplog.text


# fails because default string doesn't match the format - note that this is not handled by Pydantic (unless a user sets their own ConfigDict flag)
class MismatchedFormat(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def mismatching_default_type(
        self, one: Annotated[datetime.datetime, Field(default='aaa')]
    ) -> int: ...


def test_mismatched_format(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(MismatchedFormat)
    assert "Default value 'aaa' does not validate against schema" in caplog.text


# fails because "json_schema_extra" is using a reserved JSON schema key 'maximum', even though this otherwise passes for Pydantic
class InvalidJsonSchema(IntersectBaseCapabilityImplementation):
    @intersect_message()
    def invalid_schema_config(
        self, one: Annotated[int, Field(json_schema_extra={'maximum': 'should be an integer'})]
    ) -> bool: ...


def test_invalid_json_schema(caplog: pytest.LogCaptureFixture):
    with pytest.raises(SystemExit):
        get_schema_helper(InvalidJsonSchema)
    assert 'Invalid JSON schema generated for INTERSECT' in caplog.text
    assert '$.maximum' in caplog.text
    assert "is not of type 'number'" in caplog.text
