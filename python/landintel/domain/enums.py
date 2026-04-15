from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD = "DEAD"


class JobType(StrEnum):
    MANUAL_URL_SNAPSHOT = "MANUAL_URL_SNAPSHOT"
    CSV_IMPORT_SNAPSHOT = "CSV_IMPORT_SNAPSHOT"
    LISTING_SOURCE_RUN = "LISTING_SOURCE_RUN"
    LISTING_CLUSTER_REBUILD = "LISTING_CLUSTER_REBUILD"


class SourceFreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class SourceParseStatus(StrEnum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ConnectorType(StrEnum):
    MANUAL_URL = "MANUAL_URL"
    CSV_IMPORT = "CSV_IMPORT"
    PUBLIC_PAGE = "PUBLIC_PAGE"


class ComplianceMode(StrEnum):
    MANUAL_ONLY = "MANUAL_ONLY"
    CSV_ONLY = "CSV_ONLY"
    COMPLIANT_AUTOMATED = "COMPLIANT_AUTOMATED"
    BLOCKED = "BLOCKED"


class ListingType(StrEnum):
    LAND = "LAND"
    LAND_WITH_BUILDING = "LAND_WITH_BUILDING"
    GARAGE_COURT = "GARAGE_COURT"
    REDEVELOPMENT_SITE = "REDEVELOPMENT_SITE"
    UNKNOWN = "UNKNOWN"


class PriceBasisType(StrEnum):
    GUIDE_PRICE = "GUIDE_PRICE"
    ASKING_PRICE = "ASKING_PRICE"
    OFFERS_OVER = "OFFERS_OVER"
    OFFERS_IN_EXCESS_OF = "OFFERS_IN_EXCESS_OF"
    PRICE_ON_APPLICATION = "PRICE_ON_APPLICATION"
    AUCTION_GUIDE = "AUCTION_GUIDE"
    UNKNOWN = "UNKNOWN"


class ListingStatus(StrEnum):
    LIVE = "LIVE"
    UNDER_OFFER = "UNDER_OFFER"
    AUCTION = "AUCTION"
    SOLD_STC = "SOLD_STC"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"


class DocumentType(StrEnum):
    BROCHURE = "BROCHURE"
    MAP = "MAP"
    CSV_EXPORT = "CSV_EXPORT"
    UNKNOWN = "UNKNOWN"


class DocumentExtractionStatus(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    EXTRACTED = "EXTRACTED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ListingClusterStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SINGLETON = "SINGLETON"


class AppRoleName(StrEnum):
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class StorageBackend(StrEnum):
    LOCAL = "local"
    SUPABASE = "supabase"
