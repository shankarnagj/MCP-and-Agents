# Ontology `tessera-core` v1.0.0

Configurable core ontology. Edit this file (or PUT /api/ontology as ADMIN) to extend.

The ontology is **data**: edit `data/schemas/ontology.json` (or `PUT /api/ontology` as ADMIN). Ingestion mappings, search, the query builder,
entity resolution and field-level masking all read it at run time. Removing a type that is still in use is refused.

## Sensitivity levels

| Level | Meaning |
|---|---|
| `public` | Visible to all roles |
| `pii` | Personal data: masked for VIEWER |
| `restricted` | Highly sensitive: ADMIN/INVESTIGATOR only |

## Entity types

### Person

A natural person (synthetic in demo data).

Label property: `name`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `name` | string | pii | yes |  | name |
| `email` | string | pii | yes | email | email |
| `phone` | string | pii | yes | phone | phone |
| `date_of_birth` | date | restricted |  |  | dob |
| `address` | string | pii |  |  | address |
| `national_id` | string | restricted |  | national_id |  |
| `nationality` | string | public |  |  |  |
| `occupation` | string | public |  |  |  |

### Organization

Company, NGO, agency or other legal body.

Label property: `name`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `name` | string | public | yes |  | org_name |
| `registration_number` | string | public | yes | org_reg | org_reg |
| `jurisdiction` | string | public |  |  |  |
| `industry` | string | public |  |  |  |
| `address` | string | public |  |  | address |

### Account

Financial or service account.

Label property: `account_number`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `account_number` | string | pii | yes | account |  |
| `account_type` | string | public |  |  |  |
| `currency` | string | public |  |  |  |
| `opened_at` | datetime | public |  |  |  |
| `status` | string | public |  |  |  |
| `balance` | number | restricted |  |  |  |

### Device

Physical or virtual device.

Label property: `device_id`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `device_id` | string | public | yes | device |  |
| `device_type` | string | public |  |  |  |
| `os` | string | public |  |  |  |
| `fingerprint` | string | public |  | device_fp |  |

### Transaction

A financial transaction.

Label property: `transaction_id`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `transaction_id` | string | public | yes | transaction |  |
| `amount` | number | public |  |  |  |
| `currency` | string | public |  |  |  |
| `channel` | string | public |  |  |  |
| `timestamp` | datetime | public |  |  |  |
| `status` | string | public |  |  |  |

### Location

A named place with coordinates.

Label property: `name`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `name` | string | public | yes |  |  |
| `city` | string | public | yes |  |  |
| `country` | string | public |  |  |  |
| `lat` | number | public |  |  |  |
| `lon` | number | public |  |  |  |
| `category` | string | public |  |  |  |

### Address

Postal address.

Label property: `line1`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `line1` | string | pii | yes |  |  |
| `city` | string | public |  |  |  |
| `postcode` | string | public |  |  |  |
| `country` | string | public |  |  |  |

### IPAddress

IPv4/IPv6 address.

Label property: `ip`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `ip` | string | public | yes | ip |  |
| `asn` | string | public |  |  |  |
| `country` | string | public |  |  |  |

### Domain

DNS domain name.

Label property: `domain`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `domain` | string | public | yes | domain |  |
| `registrar` | string | public |  |  |  |
| `created` | date | public |  |  |  |

### Vehicle

Road vehicle.

Label property: `plate`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `plate` | string | pii | yes | plate |  |
| `make` | string | public |  |  |  |
| `model` | string | public |  |  |  |

### Shipment

A consignment of goods.

Label property: `shipment_id`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `shipment_id` | string | public | yes | shipment |  |
| `product` | string | public | yes |  |  |
| `quantity` | number | public |  |  |  |
| `status` | string | public |  |  |  |
| `origin` | string | public |  |  |  |
| `destination` | string | public |  |  |  |

### Vessel

A ship.

Label property: `name`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `name` | string | public | yes |  |  |
| `imo` | string | public | yes | imo |  |
| `flag` | string | public |  |  |  |

### Event

A discrete happening that is itself analysed as an entity.

Label property: `title`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `title` | string | public | yes |  |  |
| `event_type` | string | public |  |  |  |
| `timestamp` | datetime | public |  |  |  |

### Document

A document or file.

Label property: `title`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `title` | string | public | yes |  |  |
| `doc_type` | string | public |  |  |  |
| `sha256` | string | public |  | sha256 |  |

### Case

An external case reference.

Label property: `title`

| Property | Type | Sensitivity | Searchable | Identifier kind | ER signal |
|---|---|---|---|---|---|
| `title` | string | public | yes |  |  |
| `reference` | string | public | yes | case_ref |  |

## Relationship types

| Type | From | To | Symmetric | Description |
|---|---|---|---|---|
| `OWNS` | Person, Organization | Account, Device, Vehicle, Vessel, Domain, Organization |  | Source owns/holds target. |
| `WORKS_FOR` | Person | Organization |  | Person works for organisation. |
| `EMPLOYED_BY` | Person | Organization |  | Employment (HR-sourced). |
| `CONTROLS` | Person, Organization | Organization, Account |  | Beneficial / effective control. |
| `INITIATED` | Account | Transaction |  | Account initiated a transaction. |
| `TRANSFERRED_TO` | Transaction, Account | Account, Organization |  | Value moved to target. |
| `TRANSACTED_WITH` | Account, Person, Organization | Account, Person, Organization | yes | Aggregated trading relationship. |
| `LOCATED_AT` | * | Location, Address |  | Entity located at place. |
| `REGISTERED_AT` | Organization, Person, Vessel, Vehicle | Address, Location |  | Registered address. |
| `CONNECTED_TO` | Device, IPAddress, Account | IPAddress, Domain, Device |  | Network connection. |
| `USED` | Account, Person | Device |  | Entity used a device. |
| `COMMUNICATED_WITH` | Person, Device, Organization | Person, Device, Organization | yes | Communication. |
| `VISITED` | Person, Device, Vehicle, Vessel | Location |  | Entity was at a location. |
| `RESOLVES_TO` | Domain | IPAddress |  | DNS resolution. |
| `SHIPPED_BY` | Shipment | Organization |  | Shipment sent by supplier. |
| `SHIPPED_TO` | Shipment | Organization |  | Shipment destination party. |
| `CARRIED_BY` | Shipment | Vessel, Vehicle |  | Shipment carried by vessel/vehicle. |
| `PASSED_THROUGH` | Shipment, Vessel | Location |  | Shipment/vessel passed through location. |
| `ASSOCIATED_WITH` | * | * | yes | Generic association. |
| `DERIVED_FROM` | * | * |  | Derivation lineage between entities. |
| `MENTIONS` | Document | * |  | Document mentions entity. |
| `PART_OF` | * | Case, Organization |  | Membership. |

## Event types

`login`, `logout`, `auth_failure`, `transaction`, `device_connection`, `location_change`, `shipment_departure`, `shipment_arrival`, `port_call`, `alert`, `incident`, `communication`, `process_start`, `dns_query`, `account_opened`, `maintenance`

## Common fields

Every **entity** stores `id, type, properties, source_ids, created_at, updated_at, confidence, provenance, epistemic_status`.
Every **relationship** stores `id, source, target, relationship_type, timestamp, confidence, source_records, provenance, epistemic_status, analyst_modifications`.
Every **event** stores `timestamp, start_time, end_time, entity_ids, location, event_type, source`.
