# 产线代码模板

## 使用规则
- 需要给出实现方案时，优先从本文件选择接近的模板再落地到具体业务。
- 模板只提供稳定骨架，不替代业务建模、错误语义和测试策略。
- 使用模板时，必须同时说明哪些部分是通用骨架，哪些部分需要按业务改写。

## 目录
- ViewModel 模板
- UseCase 模板
- Repository 模板
- APIClient 模板
- Coordinator 模板
- Actor 模板

## ViewModel 模板
适用于：
- UIKit MVVM
- SwiftUI 状态驱动页面
- 列表、表单、详情页状态编排

```swift
import Foundation

@MainActor
final class FeatureViewModel: ObservableObject {
    @Published private(set) var viewState: ViewState = .idle

    private let useCase: FeatureUseCaseProtocol
    private var loadTask: Task<Void, Never>?

    init(useCase: FeatureUseCaseProtocol) {
        self.useCase = useCase
    }

    deinit {
        loadTask?.cancel()
    }

    func load() {
        loadTask?.cancel()
        loadTask = Task { [weak self] in
            guard let self else { return }
            self.viewState = .loading

            do {
                let output = try await self.useCase.execute()
                guard !Task.isCancelled else { return }
                self.viewState = .loaded(output)
            } catch is CancellationError {
                return
            } catch {
                self.viewState = .failed(.from(error))
            }
        }
    }
}

extension FeatureViewModel {
    enum ViewState: Equatable {
        case idle
        case loading
        case loaded(FeatureOutput)
        case failed(ViewError)
    }
}
```

要求：
- ViewModel 只编排状态，不做网络细节和持久化细节。
- 任务必须可取消。
- 错误必须映射为 UI 可消费的语义。

## UseCase 模板
适用于：
- 业务规则聚合
- 多数据源编排
- 领域层输入输出建模

```swift
import Foundation

protocol FeatureUseCaseProtocol {
    func execute() async throws -> FeatureOutput
}

struct FeatureUseCase: FeatureUseCaseProtocol {
    private let repository: FeatureRepositoryProtocol

    init(repository: FeatureRepositoryProtocol) {
        self.repository = repository
    }

    func execute() async throws -> FeatureOutput {
        let entity = try await repository.fetch()
        return FeatureOutput(entity: entity)
    }
}
```

要求：
- UseCase 承载业务规则，不承载 UI 逻辑。
- 输入输出必须显式建模。

## Repository 模板
适用于：
- 远端 + 本地缓存聚合
- 解耦 Service 与业务层

```swift
import Foundation

protocol FeatureRepositoryProtocol {
    func fetch() async throws -> FeatureEntity
}

struct FeatureRepository: FeatureRepositoryProtocol {
    private let remote: FeatureRemoteDataSourceProtocol
    private let cache: FeatureCacheProtocol

    init(
        remote: FeatureRemoteDataSourceProtocol,
        cache: FeatureCacheProtocol
    ) {
        self.remote = remote
        self.cache = cache
    }

    func fetch() async throws -> FeatureEntity {
        if let cached = try? cache.read() {
            return cached
        }

        let entity = try await remote.fetch()
        try? cache.write(entity)
        return entity
    }
}
```

要求：
- Repository 屏蔽数据来源差异。
- 缓存策略必须按业务语义定义，不得静默污染状态。

## APIClient 模板
适用于：
- `URLSession + async/await`
- 强类型错误建模

```swift
import Foundation

protocol APIClientProtocol {
    func send<T: Decodable>(_ endpoint: Endpoint<T>) async throws -> T
}

struct APIClient: APIClientProtocol {
    private let session: URLSession
    private let decoder: JSONDecoder

    init(
        session: URLSession = .shared,
        decoder: JSONDecoder = JSONDecoder()
    ) {
        self.session = session
        self.decoder = decoder
    }

    func send<T: Decodable>(_ endpoint: Endpoint<T>) async throws -> T {
        let request = try endpoint.makeURLRequest()
        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw NetworkError.invalidResponse
        }

        guard 200..<300 ~= httpResponse.statusCode else {
            throw NetworkError.httpStatus(httpResponse.statusCode)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw NetworkError.decoding(error)
        }
    }
}
```

要求：
- 请求构建、发送、解码、错误分层必须分清。
- 不得在 APIClient 中混入业务降级逻辑。

## Coordinator 模板
适用于：
- UIKit 导航编排
- Feature 路由解耦

```swift
import UIKit

protocol Coordinator: AnyObject {
    func start()
}

final class FeatureCoordinator: Coordinator {
    private let navigationController: UINavigationController
    private let factory: FeatureSceneFactoryProtocol

    init(
        navigationController: UINavigationController,
        factory: FeatureSceneFactoryProtocol
    ) {
        self.navigationController = navigationController
        self.factory = factory
    }

    func start() {
        let viewController = factory.makeFeatureScene()
        navigationController.pushViewController(viewController, animated: true)
    }
}
```

要求：
- 页面不直接拼装下一个页面。
- Coordinator 负责路由，不承载业务计算。

## Actor 模板
适用于：
- 共享可变状态隔离
- Token 刷新、内存缓存、请求去重

```swift
import Foundation

actor FeatureStore<Value> {
    private var storage: Value

    init(initialValue: Value) {
        self.storage = initialValue
    }

    func read() -> Value {
        storage
    }

    func update(_ transform: (inout Value) -> Void) {
        transform(&storage)
    }
}
```

要求：
- actor 只承担隔离职责，不扩大为万能容器。
- 需要跨域传递的数据必须保持语义清晰。
