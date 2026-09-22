plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Optional build-time server URL: -Pallin1ServerUrl=https://example.com
val defaultServerUrl: String = (project.findProperty("allin1ServerUrl") as String?)?.trim().orEmpty()

android {
    namespace = "com.allin1.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.allin1.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
        resourceConfigurations += listOf("en")
        buildConfigField("String", "DEFAULT_SERVER_URL", "\"$defaultServerUrl\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        debug {
            // No applicationIdSuffix: the debug APK installs as the same app
            // identity, so sideloading "just works" with one icon on the device.
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.webkit:webkit:1.9.0")
}
