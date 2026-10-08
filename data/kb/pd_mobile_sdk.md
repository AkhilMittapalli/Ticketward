---
doc_key: pd_mobile_sdk
doc_type: product_doc
title: "Mobile SDK Documentation for iOS and Android"
product_areas:
  - mobile_apps
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-22"
effective_from: "2026-07-26"
effective_to: null
---

## Overview

The Taskmoor Mobile SDK provides native libraries for integrating Taskmoor functionality into iOS and Android applications. The SDK wraps the REST API v2 with platform-native interfaces, handles authentication, caching, and offline queuing. Mobile SDK access requires a Starter plan or above.

## Platform Support

| Platform | Minimum Version | Language | Package |
|----------|:--------------:|----------|---------|
| iOS | 15.0+ | Swift 5.9+ | `TaskmoorSDK` via Swift Package Manager |
| Android | API 26+ (Android 8.0) | Kotlin 1.9+ | `com.taskmoor:sdk` via Maven Central |

## Installation

### iOS (Swift Package Manager)

Add the Taskmoor SDK to your Xcode project:

1. In Xcode, go to **File > Add Package Dependencies**.
2. Enter the repository URL: `https://github.com/taskmoor/ios-sdk.git`
3. Select version `2.x` and add the `TaskmoorSDK` library to your target.

### Android (Gradle)

Add the dependency to your module-level `build.gradle.kts`:

```kotlin
dependencies {
    implementation("com.taskmoor:sdk:2.4.0")
}
```

## Initialization

### iOS

```swift
import TaskmoorSDK

let config = TaskmoorConfig(
    apiToken: "tm_test_mobile_abc123",
    environment: .sandbox
)

let taskmoor = TaskmoorClient(config: config)
```

### Android

```kotlin
import com.taskmoor.sdk.TaskmoorClient
import com.taskmoor.sdk.TaskmoorConfig

val config = TaskmoorConfig.Builder()
    .apiToken("tm_test_mobile_abc123")
    .environment(TaskmoorConfig.Environment.SANDBOX)
    .build()

val taskmoor = TaskmoorClient(context, config)
```

Use `.sandbox` / `Environment.SANDBOX` during development and `.production` / `Environment.PRODUCTION` with `tm_live_` tokens for release builds.

## Core API Operations

### Fetching Tasks

#### iOS

```swift
let tasks = try await taskmoor.tasks.list(
    projectId: "proj_001",
    status: .inProgress,
    limit: 25
)

for task in tasks.data {
    print("\(task.id): \(task.title) - \(task.status)")
}
```

#### Android

```kotlin
val tasks = taskmoor.tasks().list(
    projectId = "proj_001",
    status = TaskStatus.IN_PROGRESS,
    limit = 25
)

tasks.data.forEach { task ->
    Log.d("Taskmoor", "${task.id}: ${task.title} - ${task.status}")
}
```

### Creating a Task

#### iOS

```swift
let newTask = try await taskmoor.tasks.create(
    CreateTaskRequest(
        title: "Fix login screen crash",
        projectId: "proj_001",
        priority: .high,
        assigneeId: "usr_007",
        labels: ["mobile", "bug"]
    )
)
```

#### Android

```kotlin
val newTask = taskmoor.tasks().create(
    CreateTaskRequest(
        title = "Fix login screen crash",
        projectId = "proj_001",
        priority = TaskPriority.HIGH,
        assigneeId = "usr_007",
        labels = listOf("mobile", "bug")
    )
)
```

### Adding a Comment

#### iOS

```swift
let comment = try await taskmoor.comments.create(
    CreateCommentRequest(
        taskId: "task_042",
        body: "Tested on iOS 17 and Android 14. Both working correctly."
    )
)
```

### Listing Projects

#### Android

```kotlin
val projects = taskmoor.projects().list(
    status = ProjectStatus.ACTIVE,
    limit = 50
)
```

## Pagination

The SDK handles cursor-based pagination through iterator patterns:

### iOS

```swift
for try await page in taskmoor.tasks.listAll(projectId: "proj_001") {
    for task in page.data {
        processTask(task)
    }
}
```

### Android

```kotlin
taskmoor.tasks().listAll(projectId = "proj_001").collect { page ->
    page.data.forEach { task ->
        processTask(task)
    }
}
```

## Offline Support

The SDK queues write operations when the device is offline and synchronizes them when connectivity is restored.

### Enabling Offline Mode

#### iOS

```swift
let config = TaskmoorConfig(
    apiToken: "tm_test_mobile_abc123",
    environment: .sandbox,
    offlineMode: .queueWrites
)
```

#### Android

```kotlin
val config = TaskmoorConfig.Builder()
    .apiToken("tm_test_mobile_abc123")
    .environment(TaskmoorConfig.Environment.SANDBOX)
    .offlineMode(OfflineMode.QUEUE_WRITES)
    .build()
```

Queued operations are persisted to device storage and replayed in order when the network becomes available. Conflicts are resolved using last-writer-wins semantics.

## Error Handling

The SDK translates API errors into platform-native exceptions:

### iOS

```swift
do {
    let task = try await taskmoor.tasks.get(id: "task_999")
} catch let error as TaskmoorAPIError {
    switch error.code {
    case .authenticationFailed:  // API_ERR_401
        // Handle invalid token
    case .rateLimited:           // API_ERR_429
        // Wait and retry
    case .notFound:
        // Task does not exist
    default:
        print("Error: \(error.message)")
    }
}
```

### Android

```kotlin
try {
    val task = taskmoor.tasks().get("task_999")
} catch (e: TaskmoorApiException) {
    when (e.errorCode) {
        "API_ERR_401" -> { /* Handle invalid token */ }
        "API_ERR_429" -> { /* Wait and retry */ }
        else -> Log.e("Taskmoor", "Error: ${e.message}")
    }
}
```

## Rate Limits

The Mobile SDK respects the same rate limits as the REST API. When a `429` response is received, the SDK automatically waits for the `retry_after` duration and retries the request up to 3 times before surfacing the error to the calling code.

## File Attachment Limits

File uploads through the SDK follow the same per-plan limits: Free (10 MB), Starter (100 MB), Business (250 MB), Enterprise (1 GB).

## Push Notifications

The SDK can register for push notifications to receive real-time task updates:

### iOS

```swift
taskmoor.notifications.register(deviceToken: apnsToken, events: [.taskAssigned, .commentCreated])
```

### Android

```kotlin
taskmoor.notifications().register(fcmToken = token, events = listOf(NotificationEvent.TASK_ASSIGNED, NotificationEvent.COMMENT_CREATED))
```
