param(
    [switch]$Probe,
    [switch]$Diagnostic,
    [ValidateSet('Wake', 'Dictation', 'Both')]
    [string]$Mode = 'Both'
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Write-LioraJson {
    param([hashtable]$Value)
    [Console]::Out.WriteLine(($Value | ConvertTo-Json -Compress -Depth 5))
    [Console]::Out.Flush()
}

function Get-LioraRecognizers {
    param($Installed)

    $selected = @()
    foreach ($culture in @('zh-CN', 'en-US')) {
        $match = $Installed | Where-Object { $_.Culture.Name -eq $culture } | Select-Object -First 1
        if ($null -ne $match) { $selected += $match }
    }
    if ($selected.Count -eq 0 -and $Installed.Count -gt 0) {
        $selected += $Installed | Select-Object -First 1
    }
    return @($selected)
}

function Get-WakePhrases {
    param([string]$Culture)

    if ($Culture -eq 'en-US') {
        return [string[]]@('Hi Liora', 'Hey Liora', 'Hi Leora', 'Hey Leora')
    }
    return [string[]]@(
        'Hi Liora',
        (-join @([char]0x55E8, [char]0x8389, [char]0x5965, [char]0x62C9)),
        (-join @([char]0x55E8, [char]0x4E3D, [char]0x5965, [char]0x62C9)),
        (-join @([char]0x55E8, [char]0x91CC, [char]0x5965, [char]0x62C9)),
        (-join @([char]0x6D77, [char]0x8389, [char]0x5965, [char]0x62C9)),
        (-join @([char]0x6D77, [char]0x4E3D, [char]0x5965, [char]0x62C9)),
        (-join @([char]0x6D77, [char]0x91CC, [char]0x5965, [char]0x62C9))
    )
}

try {
    Add-Type -AssemblyName System.Speech
    $installed = @([System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers())
    $recognizerInfos = @(Get-LioraRecognizers -Installed $installed)
    if ($recognizerInfos.Count -eq 0) {
        throw 'No Windows speech recognizer is installed.'
    }

    $recognizerSummary = @($recognizerInfos | ForEach-Object {
        @{ id = $_.Id; description = $_.Description; culture = $_.Culture.Name }
    })
    if ($Probe) {
        Write-LioraJson @{ type = 'probe'; recognizers = $recognizerSummary }
        exit 0
    }

    $engines = @()
    $subscriptions = @()
    for ($index = 0; $index -lt $recognizerInfos.Count; $index++) {
        $info = $recognizerInfos[$index]
        $engine = [System.Speech.Recognition.SpeechRecognitionEngine]::new($info.Id)

        if ($Mode -eq 'Wake' -or $Mode -eq 'Both') {
            $wakeChoices = [System.Speech.Recognition.Choices]::new((Get-WakePhrases -Culture $info.Culture.Name))
            $wakeBuilder = [System.Speech.Recognition.GrammarBuilder]::new()
            $wakeBuilder.Culture = $info.Culture
            $wakeBuilder.Append($wakeChoices)
            $wakeGrammar = [System.Speech.Recognition.Grammar]::new($wakeBuilder)
            $wakeGrammar.Name = "liora-wake:$($info.Culture.Name)"
            $engine.LoadGrammar($wakeGrammar)
        }

        # Dictation is handled by SenseVoice in the app. Keep this legacy
        # mode on one engine only so multiple language engines do not duplicate it.
        if (($Mode -eq 'Dictation' -or $Mode -eq 'Both') -and $index -eq 0) {
            $dictation = [System.Speech.Recognition.DictationGrammar]::new()
            $dictation.Name = 'liora-dictation'
            $engine.LoadGrammar($dictation)
        }

        $engine.SetInputToDefaultAudioDevice()
        $messageData = @{
            culture = $info.Culture.Name
            recognizer = $info.Description
        }
        $subscription = Register-ObjectEvent `
            -InputObject $engine `
            -EventName SpeechRecognized `
            -MessageData $messageData `
            -Action {
                $result = $Event.SourceEventArgs.Result
                if ($null -ne $result -and -not [string]::IsNullOrWhiteSpace($result.Text)) {
                    $payload = @{
                        type = 'recognized'
                        text = $result.Text
                        confidence = [Math]::Round($result.Confidence, 4)
                        grammar = $result.Grammar.Name
                        culture = $Event.MessageData.culture
                        recognizer = $Event.MessageData.recognizer
                    }
                    [Console]::Out.WriteLine(($payload | ConvertTo-Json -Compress))
                    [Console]::Out.Flush()
                }
            }
        $subscriptions += $subscription
        $engines += $engine
    }

    $audioLevelSubscription = $null
    $speechDetectedSubscription = $null
    if ($Diagnostic) {
        $diagnosticEngine = $engines[0]
        $audioLevelSubscription = Register-ObjectEvent -InputObject $diagnosticEngine -EventName AudioLevelUpdated -Action {
            [Console]::Out.WriteLine((@{ type = 'level'; value = $Event.SourceEventArgs.AudioLevel } | ConvertTo-Json -Compress))
            [Console]::Out.Flush()
        }
        $speechDetectedSubscription = Register-ObjectEvent -InputObject $diagnosticEngine -EventName SpeechDetected -Action {
            [Console]::Out.WriteLine((@{ type = 'speech-detected' } | ConvertTo-Json -Compress))
            [Console]::Out.Flush()
        }
    }

    foreach ($engine in $engines) {
        $engine.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
    }
    Write-LioraJson @{ type = 'ready'; recognizers = $recognizerSummary; mode = $Mode }

    try {
        while ($true) {
            $event = Wait-Event -Timeout 1
            if ($null -ne $event) {
                Remove-Event -EventIdentifier $event.EventIdentifier -ErrorAction SilentlyContinue
            }
        }
    }
    finally {
        foreach ($engine in $engines) {
            $engine.RecognizeAsyncCancel()
            $engine.Dispose()
        }
        foreach ($subscription in $subscriptions) {
            Unregister-Event -SubscriptionId $subscription.Id -ErrorAction SilentlyContinue
        }
        if ($null -ne $audioLevelSubscription) {
            Unregister-Event -SubscriptionId $audioLevelSubscription.Id -ErrorAction SilentlyContinue
        }
        if ($null -ne $speechDetectedSubscription) {
            Unregister-Event -SubscriptionId $speechDetectedSubscription.Id -ErrorAction SilentlyContinue
        }
    }
}
catch {
    Write-LioraJson @{ type = 'error'; message = $_.Exception.Message }
    exit 1
}
