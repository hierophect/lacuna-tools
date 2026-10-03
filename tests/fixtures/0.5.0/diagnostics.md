# Lacuna Deck Language 0.5.0 diagnostic examples

These examples are fragments. Assume that omitted surrounding declarations are
otherwise valid. Diagnostic wording is implementation-defined, but severity and
compilation outcome are normative.

## Warnings

Warnings do not prevent compiled JSON from being produced.

### Exact duplicate Selectable

```lacu
## item
>key;english
apple;apple

## item
>key;english
apple;apple
```

The second `apple;apple` is reported and omitted from compiled JSON.

### Ambiguous lookup

```lacu
## noun
>key;english;usage
television;television;general
television;television;physical object

# Groups
televisions;noun;key;{television}
```

The Group lookup emits an ambiguity warning and uses the first Selectable in
compilation order.

### Repeated vocabulary declaration

```lacu
## lesson_1
>english
>vocab;item;key;{apple}

## lesson_2
>english
>vocab;item;key;{apple}
```

The `lesson_2` declaration emits a warning and is absent from its compiled
`vocab` array. The `lesson_1` declaration remains effective.

### Trailing ASCII spaces

A decoded Selectable Variant value or Template Side ending in one or more
ASCII spaces emits a warning. The spaces remain in compiled JSON because they
are significant in 0.5.0.

### Missing final line ending

A source file whose last physical record ends directly at end-of-file emits a
warning but remains valid in 0.5.0.

## Errors

Any error prevents a compiled interchange document from being emitted.

### Category schema redefinition

```lacu
## noun
>key;english
apple;apple

## noun
>key;english;e_plural
apple;apple;apples
```

The second header attempts to change the ordered Variant schema.

### Duplicate Chapter name

```lacu
## lesson_1
>english
```

Repeating `lesson_1` anywhere else in the layered Deck is an error.

### Duplicate Side label

```lacu
## lesson_1
>english;english
```

Modifiers are removed before labels are compared, so `>english;~english` is
also invalid.

### Invalid Side modifiers

```lacu
>^english;^japanese
>^~english;japanese
>~^english;japanese
```

Only one Side may be marked `^`. A label cannot combine `^` and `~`, and a
Chapter cannot make every Side supplementary.

### Supplementary first Side without a forced Side

```lacu
>~notes;english
```

When no label has `^`, the first declared label becomes compiled Side zero and
must be non-supplementary. If another label is marked `^`, compilation moves
that non-supplementary label and its Sides to index zero instead.

### Repeated Group on one Side

```lacu
[people] introduced [people].
```

Version 0.5.0 cannot state whether the two occurrences should contain the same
or different Selectables. Repetition on one Side is therefore invalid.

### Selection introduced after Side zero

```lacu
## lesson_1
>english;japanese
{
    A person arrived.
    [people:japanese]が来ました。
}
```

The later Side cannot introduce `people` because Side zero does not establish
that selection.

### More than one Pairgroup

```lacu
<people_and_places:person> saw <objects_and_colors:object>.
```

A Template may reference multiple aliases from one Pairgroup, but not two
distinct Pairgroups.

### Forbidden literal characters

```lacu
Alice & Bob arrived.
two + two
Use [literal brackets].
Use “curly quotes”.
```

All four lines are invalid literal content. Diagnostics for the first two also
recommend “and” and “plus.” Structural brackets remain valid as replacement
syntax when their contents form a valid Group reference.

### Pairgroup column count

```lacu
## relation
>person=group
people
```

A Pairgroup must define at least two columns.

### Pairgroup row width

```lacu
## relation
>person=group;place=group
people
```

Every row must contain exactly one value per Pairgroup column.

### Template Side count

```lacu
## lesson_1
>english;japanese;~notes
{
    Hello.
    こんにちは。
}
```

Every Template in the Chapter must contain exactly three Sides.

### Unknown interchange property

The structurally valid JSON document
[`invalid-extra-property.json`](invalid-extra-property.json) fails the 0.5.0
JSON Schema because `syntax_version` is not part of the frozen interchange
shape. Version agreement is external in 0.5.0, and unknown properties are
invalid.

### Supplementary compiled Side zero

The JSON document
[`invalid-first-supplementary.json`](invalid-first-supplementary.json) fails
the 0.5.0 JSON Schema because the first compiled Side label is supplementary.

### Side labels equal after normalization

The JSON document
[`semantic-invalid-side-labels.json`](semantic-invalid-side-labels.json)
passes the structural JSON Schema but is not a valid 0.5.0 interchange
document. After `~` is removed, its `english` and `~english` labels are equal.
Consumers must apply this semantic validation in addition to the schema.

## Quoting examples

These records are valid:

```lacu
key;"contains; a semicolon";"She said ""hello""."
```

They compile to the three strings `key`, `contains; a semicolon`, and
`She said "hello".`. A physical newline inside a quoted field is invalid.
