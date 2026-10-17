package com.tunnathub.app;

import java.util.Arrays;
import java.util.Collections;

public class RcStickMapperTest {
    private static final float EPSILON = 0.0001f;

    public static void main(String[] args) {
        mapsRhRvLvLhToRightAndLeftSticks();
        clampsValuesOutsideRawStickRange();
        centersMissingRawChannels();
    }

    private static void mapsRhRvLvLhToRightAndLeftSticks() {
        RcStickPositions positions = RcStickMapper.fromRawChannels(
                Arrays.asList(330, -660, 165, -330));

        assertEquals(-0.5f, positions.getLeft().getX(), EPSILON);
        assertEquals(0.25f, positions.getLeft().getY(), EPSILON);
        assertEquals(0.5f, positions.getRight().getX(), EPSILON);
        assertEquals(-1.0f, positions.getRight().getY(), EPSILON);
    }

    private static void clampsValuesOutsideRawStickRange() {
        RcStickPositions positions = RcStickMapper.fromRawChannels(
                Arrays.asList(900, -900, 1200, -1200));

        assertEquals(-1.0f, positions.getLeft().getX(), EPSILON);
        assertEquals(1.0f, positions.getLeft().getY(), EPSILON);
        assertEquals(1.0f, positions.getRight().getX(), EPSILON);
        assertEquals(-1.0f, positions.getRight().getY(), EPSILON);
    }

    private static void centersMissingRawChannels() {
        RcStickPositions positions = RcStickMapper.fromRawChannels(Collections.emptyList());

        assertEquals(0.0f, positions.getLeft().getX(), EPSILON);
        assertEquals(0.0f, positions.getLeft().getY(), EPSILON);
        assertEquals(0.0f, positions.getRight().getX(), EPSILON);
        assertEquals(0.0f, positions.getRight().getY(), EPSILON);
    }

    private static void assertEquals(float expected, float actual, float epsilon) {
        if (Math.abs(expected - actual) > epsilon) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
    }
}
