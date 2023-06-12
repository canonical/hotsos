# Writing Events

The files under this directory contain "event" definitions which are basically
regex patterns associated with an event name. Events are coupled with a callback
function which is called and passed any search results matched using the pattern
associated with the event.

Event callbacks will typically use hotsos.core.ycheck.events.EventProcessingUtils
to categorise events for display in the summary. Search patterns using this
method must have at least one result group defined and can optionally have more.
Groups are used as follows; if a single group is used it must match the date
and the events will be tallied by date e.g.

2023-01-01: 10
2023-01-02: 23
2023-01-03: 4

The other way is to have three groups such that group 1 is date, group 2 is time
and group 3 matches a value this can be used as the root key for a tally e.g.

val1:
  2023-01-01: 10
  2023-01-02: 23
  2023-01-03: 4
val2:
  2023-01-01: 3
  2023-01-02: 4
  2023-01-03: 10

See the class docstring for more information on how to use it.
