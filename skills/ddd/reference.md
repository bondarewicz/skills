# Strategic DDD reference

Read this when deciding where a boundary goes, how contexts talk, or whether DDD is worth it here.
SKILL.md has the tactical rules the hook enforces; this file has the thinking behind them.

## Subdomains decide investment

Classify each subdomain before choosing how to model it:

| Type | What it is | Invest |
|---|---|---|
| Core | The thing the business wins with: complex, volatile, differentiating | Build in house, best people, rich model |
| Supporting | Necessary, simple, not differentiating | Simplest model that works, or outsource |
| Generic | Solved problem everyone has (auth, billing, email) | Buy or adopt |

Classification is not permanent: a supporting subdomain can become core when the business starts
competing on it, and a core one becomes generic once the market commoditises it. Re-check at each
planning cycle.

## Model type per subdomain (Khononov)

Match the modelling pattern to the subdomain's complexity, not to taste:

| Logic | Pattern | C# shape |
|---|---|---|
| Simple, few rules | Transaction script | A handler with straight-line code against the database |
| Simple, CRUD-ish | Active record | Entities with public state, persistence-aware |
| Complex invariants | Domain model | Aggregates, value objects, domain events; the SKILL.md rules |
| Complex plus audit or time travel | Event-sourced domain model | State rebuilt from the aggregate's event stream |

Using a domain model for a supporting subdomain is waste. Using active record for a core one is debt.

## Bounded contexts

A bounded context is the scope in which one model and one ubiquitous language hold. The boundary
is a project or module boundary with enforced references, not a folder. Two contexts never share
an entity class: each models the same real-world thing in its own terms (a `Customer` in Sales has
a credit limit; in Shipping it has delivery addresses).

Team Topologies alignment: one team owns a context end to end. A context split across teams or a
team owning many unrelated contexts both show up as integration pain.

**Bounded Context Canvas** (DDD Crew): name, purpose, strategic classification (domain role,
business model, evolution stage), inbound and outbound communication with the collaborator and
message types, ubiquitous language, business decisions, assumptions, verification metrics, open
questions. Fill it in a workshop before writing the first class.

**Aggregate Design Canvas** (DDD Crew): name, description, state transitions, enforced invariants,
corrective policies, handled commands, created events, throughput (commands and events per instance
per unit time), size. The throughput and size rows are what tell you an aggregate is too big.

## Context mapping patterns

How two contexts relate, in order from closest to most distant:

- **Partnership**: two teams evolve their contexts together, release together.
- **Shared kernel**: a small shared model both own; keep it tiny, it couples releases.
- **Customer–supplier**: upstream serves downstream's needs by agreement.
- **Conformist**: downstream adopts the upstream model as is, no negotiation.
- **Anticorruption layer (ACL)**: downstream translates the upstream model into its own, protecting
  itself from a messy or changing upstream. The default when integrating a legacy or third-party system.
- **Open host service (OHS)** with a **published language**: upstream exposes a stable, documented
  protocol for many consumers.
- **Separate ways**: no integration, duplicate the small bit of functionality instead.
- **Big ball of mud**: mark the region that has no boundaries; integrate with it through an ACL only.

Draw the map with the DDD Crew context-mapping cheatsheet; upstream and downstream, and which
pattern sits on each line.

## Balancing coupling (Khononov)

Coupling has three dimensions. **Integration strength** is how much knowledge crosses the boundary:
intrusive (reaching into internals) > functional (shared business rules) > model (shared data
model) > contract (an integration-specific model). **Distance** is how far apart the coupled parts
live: same method, class, module, service, organisation. **Volatility** is how often the upstream
changes.

Pain comes from strength multiplied by volatility, and is amplified by distance. Reduce strength
across distant boundaries (contract coupling, published language, ACL); accept high strength only
close together (inside an aggregate, inside a module). A stable, generic upstream may be coupled
strongly without harm; a volatile core must be reached through contracts.

## Modular monolith first

Start with bounded contexts as modules in one deployable: one project per context, references only
through contract projects, one database with one schema per context, integration via in-process
domain events. Extract a context to a service only on evidence: independent scaling, independent
release cadence, or a team boundary. The module boundaries are what make extraction cheap later.

## Discovery

Run EventStorming (big-picture, then process, then design level) before modelling; the
`eventstorming` skill builds the Miro board. Pivotal events and swimlane changes on the board are
the first candidates for context boundaries; clusters of commands around the same data are
aggregate candidates.

## When not to use DDD

- A supporting or generic subdomain: use transaction script or active record and move on.
- No access to domain experts: the ubiquitous language cannot form, the model will be invented.
- A prototype, a one-off, a data pipeline, a reporting store.
- A team of one or two on a small app where the overhead exceeds the complexity it tames.

## Sources

- Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software*, 2003.
- Vernon, *Implementing Domain-Driven Design*, 2013; *Domain-Driven Design Distilled*, 2016.
- Khononov, *Learning Domain-Driven Design*, O'Reilly 2021; *Balancing Coupling in Software
  Design*, Addison-Wesley 2024.
- DDD Crew: Bounded Context Canvas, Aggregate Design Canvas, Context Mapping cheatsheet
  (github.com/ddd-crew).
- Brandolini, *Introducing EventStorming*, Leanpub.
- Microsoft, *.NET Microservices: Architecture for Containerized .NET Applications*, chapter on DDD
  and CQRS patterns (learn.microsoft.com/dotnet/architecture/microservices).
