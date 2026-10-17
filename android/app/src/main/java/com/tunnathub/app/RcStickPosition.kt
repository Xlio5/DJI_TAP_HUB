package com.tunnathub.app

data class RcStickPosition(val x: Float, val y: Float)

data class RcStickPositions(
    val left: RcStickPosition,
    val right: RcStickPosition,
)

object RcStickMapper {
    private const val RAW_FULL_SCALE = 660f

    @JvmStatic
    fun fromRawChannels(rawChannels: List<Int>): RcStickPositions {
        fun normalized(index: Int): Float =
            ((rawChannels.getOrNull(index) ?: 0) / RAW_FULL_SCALE).coerceIn(-1f, 1f)

        return RcStickPositions(
            left = RcStickPosition(x = normalized(3), y = normalized(2)),
            right = RcStickPosition(x = normalized(0), y = normalized(1)),
        )
    }
}
