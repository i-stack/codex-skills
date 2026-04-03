# UI 状态模式

## 目录
- 使用规则
- 状态分层
- 页面状态机
- 列表状态模式
- 表单状态模式
- 异步回写规则
- 空态与错误态
- 常见反模式

## 使用规则
- 涉及页面状态、列表状态、表单状态、加载状态、错误状态时，必须先定义状态模型。
- 不得使用多个布尔值拼凑复杂页面状态。
- 不得让 View、ViewModel、Service 同时维护一份页面状态。

## 状态分层
固定拆分为三层：
- 领域状态：业务是否成立、数据是否有效
- 页面状态：页面当前处于加载、成功、失败、空态、刷新、分页哪一态
- 组件状态：弹窗、按钮禁用、输入焦点、局部 loading

要求：
- 页面状态由 ViewModel 统一产出。
- 组件状态不得反向污染领域状态。
- 列表项局部状态不得覆盖整个页面状态。

## 页面状态机
推荐骨架：

```swift
enum PageState: Equatable {
    case idle
    case loading
    case loaded(ContentState)
    case empty(EmptyState)
    case failed(ViewError)
}
```

要求：
- `idle`、`loading`、`loaded`、`empty`、`failed` 五态必须明确。
- 不得把空态混进失败态。
- 不得把刷新中的成功态误建模为全屏 loading。

## 列表状态模式
列表状态至少拆为：
- 首次加载状态
- 下拉刷新状态
- 分页加载状态
- 空列表状态
- 分页尾页状态
- 局部错误提示状态

要求：
- 首刷失败与分页失败分开建模。
- 下拉刷新不得清空已展示数据。
- 分页失败不得覆盖已有列表内容。
- 新刷新结果不得被旧分页结果覆盖。

推荐骨架：

```swift
struct ListViewState<Item: Equatable>: Equatable {
    var items: [Item]
    var phase: Phase
    var pagination: PaginationState

    enum Phase: Equatable {
        case idle
        case loading
        case loaded
        case empty
        case failed(ViewError)
    }

    enum PaginationState: Equatable {
        case idle
        case loadingNextPage
        case noMoreData
        case failed(ViewError)
    }
}
```

## 表单状态模式
表单状态至少拆为：
- 输入值
- 校验状态
- 提交状态
- 提交错误
- 可交互状态

要求：
- 校验错误与提交错误分开建模。
- 本地校验失败不得伪装成服务端失败。
- 提交中状态必须禁止重复提交。
- 表单草稿状态必须定义重置和回填规则。

## 异步回写规则
- 任何异步结果回写前都必须确认任务未取消、状态未过期、页面仍然有效。
- 页面切换、列表复用、搜索关键词变化后，旧结果不得覆盖新状态。
- 过期结果必须丢弃，不做“尽力回写”。

## 空态与错误态
- 空态表示“成功返回但无数据”。
- 错误态表示“请求失败、解析失败、业务失败或关键状态不成立”。
- 空态必须有空态语义，不得使用“暂无数据”覆盖所有失败场景。
- 错误态必须提供用户动作：重试、返回、联系客服、检查网络。

## 常见反模式
- `isLoading`、`hasError`、`isEmpty`、`hasData` 四个布尔值并存
- 刷新时把列表直接清空造成闪屏
- 分页失败后把整页切到失败态
- 提交中仍允许重复点击按钮
- 搜索关键词变化后旧请求结果覆盖新结果
