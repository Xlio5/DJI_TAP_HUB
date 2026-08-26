package com.tunnathub.app.rc

/** RC 输入源读取器接口: 持续读取输入并回调 RcInputSample。 */
interface RcReader {
    suspend fun run()
}
