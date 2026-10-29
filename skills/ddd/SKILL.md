---
name: ddd
description: Use when writing or reviewing C# in a Domain folder or *.Domain project, when the ddd hook denies an edit or loads at session start, when designing an aggregate, entity, value object, domain event or bounded context, or when deciding whether a subdomain needs a domain model at all.
---

# DDD in C#

Model the business, not the database. The domain project is plain C# that knows nothing about
storage, hosting, logging or mapping. Strategy (subdomains, context maps, coupling): `reference.md`.

## Decide first
- Core subdomain → domain model (or event-sourced). Supporting → transaction script or active
  record. Generic → buy. Do not pay for a domain model where there are no rules to protect.
- One bounded context, one model, one language. Another context's entity is an ID here, never a class.
- Type and method names are the ubiquitous language verbatim: `Place()`, `OrderPlaced`, not `SetStatus(2)`.

## Dependency rule
- The domain project references no ORM, web, hosting, DI, logging, messaging, mapper or other layer.
  The ddd hook denies such usings in `Domain` folders and `*.Domain` projects.
- Needs the outside world? Declare the port (interface) in the domain, implement it in infrastructure.

## Aggregates
- One aggregate protects one set of invariants; each rule is checked in the method that could break it.
- Keep it small: only the entities that must change together. Other aggregates by ID, never as a field.
- One aggregate per transaction. Consistency across aggregates is eventual, through domain events.
- A state change that other aggregates or contexts react to raises a past-tense event.

## Building blocks
```csharp
public readonly record struct OrderId(Guid Value) { public static OrderId New() => new(Guid.NewGuid()); }
public sealed record Money(decimal Amount, Currency Currency)
{
    public decimal Amount { get; } = Amount >= 0 ? Amount : throw new NegativeMoney(Amount);
}
public sealed record OrderPlaced(OrderId OrderId, CustomerId CustomerId) : IDomainEvent;
public abstract class AggregateRoot<TId>
{
    private readonly List<IDomainEvent> _events = [];
    public TId Id { get; protected init; } = default!;
    public IReadOnlyList<IDomainEvent> Events => _events;
    protected void Raise(IDomainEvent e) => _events.Add(e);
    public void ClearEvents() => _events.Clear();
}
public sealed class Order : AggregateRoot<OrderId>
{
    private readonly List<OrderLine> _lines = [];
    public CustomerId CustomerId { get; private init; }
    public OrderStatus Status { get; private set; }
    private Order() { }   // the one concession to the ORM
    public static Order Draft(CustomerId customer) => new() { Id = OrderId.New(), CustomerId = customer };
    public void Place()
    {
        if (_lines.Count == 0) throw new EmptyOrderCannotBePlaced(Id);
        Status = OrderStatus.Placed;
        Raise(new OrderPlaced(Id, CustomerId));
    }
}

public interface IOrderRepository { Task<Order?> Get(OrderId id, CancellationToken ct); void Add(Order order); }
```
- Value object: `record` or `readonly record struct`, immutable, equal by value, validated so an
  invalid instance cannot be constructed (property initializer or static factory). Any primitive
  that carries a rule or unit (`Money`, `Currency`, `Email`, `Quantity`) becomes one. IDs are typed
  (`OrderId`), never a bare `Guid`.
- Entity: identity by ID, private setters, behaviour methods. The ORM gets a private parameterless
  constructor and nothing else: no `[Table]`, no navigation to another aggregate.
- Domain event: `record`, past tense, raised by the aggregate, dispatched after the unit of work commits.
- Repository: one interface per aggregate root, in the domain, speaking domain types. No
  `SaveChanges`, no `IQueryable`: committing is the application layer's unit-of-work port.
- Domain service: stateless, for a rule spanning aggregates. Application service: load, call, save,
  publish; no business rules.
- A broken rule is a named exception (`EmptyOrderCannotBePlaced`) or a result type, never a bare
  `InvalidOperationException`.

## Refuse
Public setters on entities · a data class plus a service holding its rules (anemic model) · an
aggregate holding another aggregate as a field · `DbContext`, `MediatR`, `ILogger`, `IMapper`,
`[Table]` in the domain · a repository per entity · `SaveChanges` on a repository · one transaction
touching two aggregates.

## Measure, don't estimate
`scripts/` is inside this skill's directory (normally `~/.claude/skills/ddd/`); use that absolute path.
`python3 scripts/ddd.py src/` lists every forbidden using in domain code, exit 1 if any.
`DDD_ALLOW=MediatR` allows a namespace; `DDD_MODE=warn` makes the hook advisory, `off` disables it.
